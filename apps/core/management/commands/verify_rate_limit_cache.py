"""Live probe of the shared rate-limit cache (run during/after a deploy).

Exercises the exact production primitive — the atomic server-side
``INCR``+``EXPIRE`` counter used by ``enforce_rate_limit`` — against the
configured rate-limit cache, with a random throw-away key: first hit creates the
counter with a positive TTL, later hits increment without extending it, the key
expires, and delete works. Prints only the backend class and per-step results;
never the cache URL or any credential. Exit status is non-zero on any failure.

    python manage.py verify_rate_limit_cache
"""

import secrets
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.services.rate_limit import build_key, get_counter
from shop_core.env_config import rate_limit_cache_problems


class Command(BaseCommand):
    help = "Verify the shared rate-limit cache (write, atomic incr, expiry, delete)."

    def handle(self, *args, **options):
        alias = getattr(settings, "RASTISI_RATE_LIMIT_CACHE_ALIAS", "ratelimit")
        production = bool(getattr(settings, "RASTISI_PRODUCTION_MODE", False))
        problems = rate_limit_cache_problems(settings.CACHES, alias=alias)
        if production and problems:
            raise CommandError("; ".join(problems))
        counter = get_counter()
        backend = settings.CACHES[alias]["BACKEND"]
        self.stdout.write(f"rate-limit cache alias={alias} backend={backend}")
        if problems:
            self.stdout.write(self.style.WARNING(
                "NOTE: not a production-grade (shared, atomic) backend — fine for local development only."
            ))

        key = build_key("verify", secrets.token_hex(8))
        window = 2
        try:
            self._step("first hit creates the counter", counter.hit(key, window) == 1)
            ttl = counter.ttl_ms(key)
            self._step("counter has a positive TTL", ttl is None or 0 < ttl <= window * 1000)
            self._step("atomic increment", counter.hit(key, window) == 2 and counter.hit(key, window) == 3)
            after = counter.ttl_ms(key)
            self._step("increments do not extend the TTL", ttl is None or after <= ttl)
            time.sleep(window + 0.5)
            self._step("expiry starts a fresh window", counter.hit(key, window) == 1)
            counter.delete(key)
            self._step("delete", counter.hit(key, window) == 1)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Class name only: connection errors may embed the credentialed URL.
            raise CommandError(f"rate-limit cache unreachable or failing: {exc.__class__.__name__}") from None
        finally:
            try:
                counter.delete(key)
            except Exception:  # noqa: BLE001
                pass
        self.stdout.write(self.style.SUCCESS("rate-limit cache OK"))

    def _step(self, label, ok):
        if not ok:
            raise CommandError(f"rate-limit cache check failed: {label}")
        self.stdout.write(f"  ok: {label}")
