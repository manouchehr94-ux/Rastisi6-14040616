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


def _spawn(action, identifier, max_attempts, window, attempts, *, url=None, start_at=0.0, extra_env=None):
    env = _worker_env(url or _URL)
    env.update(extra_env or {})
    return subprocess.Popen(
        [sys.executable, _WORKER, action, identifier, str(max_attempts), str(window), str(attempts), str(start_at)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _collect(proc, timeout=60):
    out, err = proc.communicate(timeout=timeout)
    if proc.returncode != 0:
        raise AssertionError(f"worker failed ({proc.returncode}): {err[-2000:]}")
    return json.loads(out.strip().splitlines()[-1])


class _TtlPoller(threading.Thread):
    """Samples PTTL of every counter matching ``pattern`` as fast as it can; any
    value of -1 (key exists without expiry) is recorded. A correct atomic
    INCR+EXPIRE can never be observed in that state."""

    def __init__(self, raw, pattern):
        super().__init__(daemon=True)
        self.raw, self.pattern = raw, pattern
        self.stop = threading.Event()
        self.ttl_less, self.samples = [], 0

    def run(self):
        while not self.stop.is_set():
            for key in self.raw.scan_iter(match=self.pattern, count=1000):
                ttl = self.raw.pttl(key)
                self.samples += 1
                if ttl == -1:
                    self.ttl_less.append(key)


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

    # Atomic increment + expiry on real Redis ---------------------------------------------
    def _counter_via_settings(self):
        from apps.core.services import rate_limit

        cfg = {
            "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
            "ratelimit": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _URL},
        }
        ctx = self.settings(CACHES=cfg)
        ctx.enable()
        self.addCleanup(ctx.disable)
        rate_limit._redis_counters.clear()
        self.addCleanup(rate_limit._redis_counters.clear)
        return rate_limit.get_counter(), rate_limit.build_key(self._action("direct"), "k")

    def test_first_hit_creates_count_one_with_ttl_and_later_hits_never_extend_it(self):
        counter, key = self._counter_via_settings()
        self.assertEqual(counter.hit(key, 6), 1)
        first_ttl = self.raw.pttl(key)
        self.assertTrue(0 < first_ttl <= 6000, first_ttl)
        self.assertEqual(self.raw.get(key), b"1")
        time.sleep(1.2)
        self.assertEqual(counter.hit(key, 6), 2)
        self.assertEqual(counter.hit(key, 6), 3)
        later_ttl = self.raw.pttl(key)
        self.assertTrue(0 < later_ttl <= first_ttl - 1000, (first_ttl, later_ttl))  # strictly counting down
        self.assertEqual(self.raw.get(key), b"3")

    def test_a_counter_that_somehow_has_no_ttl_is_repaired_in_the_same_atomic_step(self):
        counter, key = self._counter_via_settings()
        self.raw.set(key, 7)  # pre-existing TTL-less counter (e.g. written by older code)
        self.assertEqual(self.raw.pttl(key), -1)
        self.assertEqual(counter.hit(key, 30), 8)
        self.assertTrue(0 < self.raw.pttl(key) <= 30_000)

    def test_increment_and_expiry_are_never_separate_client_commands(self):
        """MONITOR proves INCR/EXPIRE/PTTL only ever run *inside* the Lua script
        (client_type 'lua'); the client sends EVALSHA/EVAL and nothing else for the key."""
        counter, key = self._counter_via_settings()
        counter.hit(key, 30)  # warm: loads the script
        seen, ready = [], threading.Event()
        sentinel = f"sentinel-{self.tag}"

        def watch():
            with self.raw.monitor() as monitor:
                ready.set()
                for event in monitor.listen():
                    seen.append(event)
                    if sentinel in event["command"]:
                        return

        thread = threading.Thread(target=watch, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(5))
        time.sleep(0.2)
        for _ in range(3):
            counter.hit(key, 30)
        self.raw.set(sentinel, 1, ex=5)
        thread.join(5)
        mine = [e for e in seen if key in e["command"]]
        self.assertTrue(mine, "monitor saw nothing for the counter key")
        client_side = [e["command"].split()[0].strip('"').upper() for e in mine if e["client_type"] != "lua"]
        script_side = [e["command"].split()[0].strip('"').upper() for e in mine if e["client_type"] == "lua"]
        self.assertTrue(set(client_side) <= {"EVALSHA", "EVAL"}, client_side)
        self.assertEqual(client_side.count("EVALSHA") + client_side.count("EVAL"), 3)
        self.assertIn("INCR", script_side)
        self.assertEqual(script_side.count("INCR"), 3)
        self.assertNotIn("INCR", client_side)
        self.assertNotIn("EXPIRE", client_side)
        self.assertNotIn("EXISTS", client_side)

    # Expiry boundary under real multi-process concurrency ---------------------------------
    def test_expiry_boundary_a_new_concurrent_burst_starts_a_fresh_fixed_window(self):
        action = self._action("boundary")
        window, budget, workers, per_worker = 3, 25, 8, 20
        poller = _TtlPoller(self.raw, f"*rl:v1:{action}:*")
        poller.start()
        try:
            for round_number in (1, 2, 3):
                start_at = time.time() + 6
                procs = [_spawn(action, "k", budget, window, per_worker, start_at=start_at) for _ in range(workers)]
                results = [_collect(p) for p in procs]
                self.assertEqual(sum(r["unavailable"] for r in results), 0)
                self.assertEqual(sum(r["allowed"] for r in results), budget, (round_number, results))
                keys = self._redis_keys(action)
                self.assertEqual(len(keys), 1)
                self.assertTrue(0 < self.raw.pttl(keys[0]) <= window * 1000)
                deadline = time.time() + window + 3  # let the window lapse completely
                while self.raw.exists(*keys) and time.time() < deadline:
                    time.sleep(0.1)
                self.assertEqual(self.raw.exists(*keys), 0, "window did not expire on its own")
        finally:
            poller.stop.set()
            poller.join(5)
        self.assertEqual(poller.ttl_less, [], "a live counter was observed without an expiry")
        self.assertGreater(poller.samples, 0)

    def test_continuous_hammering_across_many_expiries_never_leaves_a_ttl_less_counter(self):
        action = self._action("stress")
        poller = _TtlPoller(self.raw, f"*rl:v1:{action}:*")
        poller.start()
        start_at = time.time() + 6
        env = {"RL_DURATION": "5"}
        procs = [
            _spawn(action, "k", 10**9, 1, 0, start_at=start_at, extra_env=env) for _ in range(6)
        ]  # 1s window => ~5 expiries while 6 processes hit at full speed
        try:
            results = [_collect(p, timeout=90) for p in procs]
        finally:
            poller.stop.set()
            poller.join(5)
        self.assertEqual(sum(r["unavailable"] for r in results), 0)
        self.assertGreater(sum(r["allowed"] for r in results), 1000)
        self.assertEqual(poller.ttl_less, [])
        time.sleep(1.5)
        self.assertEqual(self._redis_keys(action), [], "a counter outlived its window")

    def test_killing_workers_mid_flight_never_leaves_a_counter_without_expiry(self):
        """SIGKILL clients at random moments of a hot loop (the crash scenario of the
        old INCR-then-EXPIRE design): every counter must still expire on its own."""
        import random
        import signal

        action = self._action("kill")
        poller = _TtlPoller(self.raw, f"*rl:v1:{action}:*")
        poller.start()
        env = {"RL_DURATION": "30", "RL_READY": "1"}
        try:
            for _ in range(3):
                batch = [_spawn(action, f"id{n}", 10**9, 1, 0, extra_env=env) for n in range(4)]
                for proc in batch:
                    self.assertEqual(proc.stdout.readline().strip(), "READY")
                time.sleep(random.uniform(0.05, 0.6))
                for proc in batch:
                    proc.send_signal(signal.SIGKILL)
                for proc in batch:
                    proc.wait(10)
                    proc.stdout.close()
                    proc.stderr.close()
        finally:
            poller.stop.set()
            poller.join(5)
        self.assertEqual(poller.ttl_less, [])
        deadline = time.time() + 5
        while self._redis_keys(action) and time.time() < deadline:
            time.sleep(0.2)
        self.assertEqual(self._redis_keys(action), [], "a killed worker left a persistent counter")

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
