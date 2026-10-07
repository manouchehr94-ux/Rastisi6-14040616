"""Standalone worker for the real-Redis multi-process rate-limit tests.

Run as a *separate interpreter* (its own Django setup, its own Redis
connections) — exactly like a gunicorn worker:

    python redis_worker.py <action> <identifier> <max_attempts> <window> <attempts> [start_at_epoch]

Environment: ``RL_DURATION`` (seconds) makes the worker hit continuously for that long instead of
``attempts`` times; ``RL_READY=1`` prints ``READY`` once Django is set up (so a test can SIGKILL it
mid-loop). Prints one JSON line: {"allowed": n, "blocked": n, "unavailable": n, "seconds": f}.
Reads the cache URL from RASTISI_RATE_LIMIT_CACHE_URL (never logged).
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")

import django  # noqa: E402

django.setup()

from apps.core.services.rate_limit import (  # noqa: E402
    RateLimitExceeded,
    RateLimitUnavailable,
    enforce_rate_limit,
)


def main():
    action, identifier, max_attempts, window, attempts = sys.argv[1:6]
    start_at = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
    duration = float(os.environ.get("RL_DURATION", "0") or 0)
    if os.environ.get("RL_READY"):
        print("READY", flush=True)
    while time.time() < start_at:  # barrier: all workers start hammering together
        time.sleep(0.0005)
    result = {"allowed": 0, "blocked": 0, "unavailable": 0}
    began = time.time()
    done = 0
    while (time.time() - began < duration) if duration else done < int(attempts):
        done += 1
        try:
            enforce_rate_limit(action, identifier, max_attempts=int(max_attempts), window_seconds=int(window))
            result["allowed"] += 1
        except RateLimitExceeded:
            result["blocked"] += 1
        except RateLimitUnavailable:
            result["unavailable"] += 1
    result["seconds"] = round(time.time() - began, 3)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
