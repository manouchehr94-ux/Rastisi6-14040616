"""Live probe of the shared rate-limit cache (run during/after a deploy).

Exercises the exact primitives the limiter relies on — write (``add``), atomic
``incr``, TTL expiry and delete — against the configured rate-limit cache, using
a random throw-away key. Prints only the backend class and per-step results;
never the cache URL or any credential. Exit status is non-zero on any failure.

    python manage.py verify_rate_limit_cache
"""

import secrets
import time

from django.conf import settings
from django.core.cache import caches
from django.core.management.base import BaseCommand, CommandError

from shop_core.env_config import rate_limit_cache_problems


class Command(BaseCommand):
    help = "Verify the shared rate-limit cache (write, atomic incr, expiry, delete)."

    def handle(self, *args, **options):
        alias = getattr(settings, "RASTISI_RATE_LIMIT_CACHE_ALIAS", "ratelimit")
        production = bool(getattr(settings, "RASTISI_PRODUCTION_MODE", False))
        problems = rate_limit_cache_problems(settings.CACHES, alias=alias)
        if production and problems:
            raise CommandError("; ".join(problems))
        store = caches[alias]
        backend = settings.CACHES[alias]["BACKEND"]
        self.stdout.write(f"rate-limit cache alias={alias} backend={backend}")
        if problems:
            self.stdout.write(self.style.WARNING(
                "NOTE: not a production-grade (shared, atomic) backend — fine for local development only."
            ))

        key = f"rl:verify:{secrets.token_hex(8)}"
        try:
            self._step("write (add NX)", store.add(key, 1, timeout=30) is True)
            self._step("add is exclusive", store.add(key, 99, timeout=30) is False)
            self._step("atomic incr", store.incr(key) == 2 and store.incr(key) == 3)
            self._step("touch/ttl", store.touch(key, 1) is True)
            time.sleep(1.5)
            self._step("expiry", store.get(key) is None)
            store.add(key, 1, timeout=30)
            store.delete(key)
            self._step("delete", store.get(key) is None)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Class name only: connection errors may embed the credentialed URL.
            raise CommandError(f"rate-limit cache unreachable or failing: {exc.__class__.__name__}") from None
        finally:
            try:
                store.delete(key)
            except Exception:  # noqa: BLE001
                pass
        self.stdout.write(self.style.SUCCESS("rate-limit cache OK"))

    def _step(self, label, ok):
        if not ok:
            raise CommandError(f"rate-limit cache check failed: {label}")
        self.stdout.write(f"  ok: {label}")
