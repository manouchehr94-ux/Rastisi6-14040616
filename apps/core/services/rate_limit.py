"""محدودیت نرخ مبتنی‌بر cache — برای فرم‌های عمومیِ سایت (ثبت‌نام، ورود،
درخواستِ OTP، فرم تماس) و چند سقفِ per-Store.

در ``apps.core`` است (نه ``apps.portal``) چون مصرف‌کننده‌هایش هم لایه‌ی
پلتفرم‌اند (``apps.portal.services.owner_otp_service``) هم لایه‌ی
مستأجر/فروشگاه (``apps.sms.services.otp_service``) — و ``apps.sms`` نباید
به‌عقب به ``apps.portal`` وابسته شود.

**الگوریتم: پنجره‌ی ثابتِ (fixed window) متکی‌بر TTL.**

* *production (Redis):* یک اسکریپتِ Lua (``EVALSHA``) سمتِ سرورِ Redis کلید را
  ``INCR`` می‌کند و — در *همان اجرا* — اگر نتیجه ``1`` بود (یا کلید TTL نداشت)
  ``EXPIRE`` می‌گذارد، و شمارش را برمی‌گرداند. Redis هر اسکریپت را به‌صورت یک
  واحدِ تقسیم‌ناپذیر اجرا می‌کند؛ پس هیچ لحظه‌ای نیست که شمارنده بدونِ
  انقضا وجود داشته باشد — حتی اگر پروسه‌ی کلاینت بلافاصله پس از ارسال بمیرد.
  هیچ ``get``/``set``، هیچ ``EXISTS``+``INCR`` و هیچ ``INCR``ِ جدا از ``EXPIRE``
  در کدِ برنامه نیست. پنجره از *اولین* تلاش شروع می‌شود، تلاش‌هایِ بعدی TTL را
  تمدید نمی‌کنند و TTLِ Redis تنها مرجعِ پایانِ پنجره است.
* *توسعه/تست (LocMem):* ``cache.add`` + ``cache.incr`` زیرِ قفلِ خودِ LocMem؛
  فقط برایِ توسعه — ``rate_limit_cache_problems`` هر backendِ غیر-Redis را در
  production رد می‌کند.

کلید: ``rl:v1:<action>:<sha256(identifier)[:32]>`` (بدونِ پیشوندِ ``:1:``ِ جنگو؛
کلاینتِ Redis مستقیم استفاده می‌شود و پیکربندی همچنان از
``CACHES["ratelimit"]`` می‌آید). شناسه *همیشه* هش می‌شود پس ایمیل/توکن/کدِ خام
هرگز در Redis نمی‌نشیند.

**سیاستِ قطعیِ backend (fail-closed):** هر خطایِ backend ``RateLimitUnavailable``
می‌دهد و فراخوان *نباید* ادامه دهد (ورودِ رمزی/ارسالِ OTP/ایمیلِ بازیابی
انجام نمی‌شود)، نه اینکه محدودیت بی‌صدا برداشته شود. استثنا: فراخوان‌هایِ
احرازشده‌یِ per-Store (سازنده‌ی فروشگاه) با ``fail_open=True`` صراحتاً اعلام
می‌کنند که این سقف مرزِ امنیتی نیست و قطعیِ Redis نباید پنل را از کار بیندازد."""

import hashlib
import logging
import re
import threading

from django.conf import settings
from django.core.cache import caches

from shop_core.env_config import REDIS_CACHE_BACKEND

logger = logging.getLogger(__name__)

_KEY_VERSION = "v1"
_ACTION_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,100}$")
_MAX_ATTEMPTS = 3

UNAVAILABLE_MESSAGE = "سرویس موقتاً در دسترس نیست؛ لطفاً چند دقیقه‌ی دیگر دوباره تلاش کنید."


class RateLimitExceeded(Exception):
    """این کنش برای این شناسه بیش از حدِ مجاز در بازه‌ی اخیر تکرار شده است."""


class RateLimitUnavailable(Exception):
    """backend مشترکِ شمارنده در دسترس نیست؛ فراخوان باید fail-closed رفتار کند
    (کارِ حساس را انجام ندهد) و پیامِ ``UNAVAILABLE_MESSAGE`` را نشان دهد."""


#: Executed atomically by Redis. ``PTTL < 0`` (no expiry) additionally covers any
#: counter that somehow exists without a TTL, so it can never block forever.
_LUA_HIT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 or redis.call('PTTL', KEYS[1]) < 0 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
"""


class _RedisCounter:
    """Production counter: one server-side Lua script = INCR + first-hit EXPIRE."""

    def __init__(self, location, options):
        self._location = location
        self._options = dict(options)
        self._lock = threading.Lock()
        self._client = None
        self._script = None

    def _connect(self):
        if self._script is None:
            with self._lock:
                if self._script is None:
                    import redis  # lazy: no import-time network, and dev needs no Redis

                    client = redis.Redis.from_url(self._location, **self._options)
                    self._script = client.register_script(_LUA_HIT)
                    self._client = client
        return self._client

    def hit(self, key: str, window_seconds: int) -> int:
        self._connect()
        return int(self._script(keys=[key], args=[int(window_seconds)]))

    def ttl_ms(self, key: str):
        return self._connect().pttl(key)

    def delete(self, key: str) -> None:
        self._connect().delete(key)


class _CacheCounter:
    """Local development/tests only (LocMem): ``add`` then ``incr``, both atomic there."""

    def __init__(self, store):
        self._store = store

    def hit(self, key: str, window_seconds: int) -> int:
        for _ in range(_MAX_ATTEMPTS):
            if self._store.add(key, 1, timeout=window_seconds):
                return 1
            try:
                return self._store.incr(key)
            except ValueError:
                continue  # expired between add() and incr(): start the window again
        raise RateLimitUnavailable("rate-limit counter did not stabilise")

    def ttl_ms(self, key: str):
        return None

    def delete(self, key: str) -> None:
        self._store.delete(key)


_redis_counters: dict = {}
_redis_counters_lock = threading.Lock()


def get_counter():
    """The counter for the configured rate-limit cache alias (no network I/O here)."""
    alias = getattr(settings, "RASTISI_RATE_LIMIT_CACHE_ALIAS", "ratelimit")
    config = settings.CACHES.get(alias) or {}
    if config.get("BACKEND") == REDIS_CACHE_BACKEND:
        options = tuple(sorted((config.get("OPTIONS") or {}).items()))
        ident = (config.get("LOCATION"), options)
        with _redis_counters_lock:
            counter = _redis_counters.get(ident)
            if counter is None:
                counter = _redis_counters[ident] = _RedisCounter(config.get("LOCATION"), options)
        return counter
    return _CacheCounter(caches[alias])


def build_key(action: str, identifier) -> str:
    if not _ACTION_RE.match(action or ""):
        raise ValueError("rate-limit action must be a short [A-Za-z0-9_.:-] token")
    digest = hashlib.sha256(str(identifier).encode("utf-8")).hexdigest()[:32]
    return f"rl:{_KEY_VERSION}:{action}:{digest}"


def enforce_rate_limit(
    action: str, identifier: str, *, max_attempts: int, window_seconds: int, fail_open: bool = False,
) -> None:
    """اگر تعداد فراخوانی‌هایِ ``action``+``identifier`` در پنجره‌ی جاری از
    ``max_attempts`` بیشتر شود ``RateLimitExceeded`` می‌دهد؛ وگرنه شمارنده را
    اتمیک یکی افزایش می‌دهد. خطایِ backend → ``RateLimitUnavailable`` (یا، فقط با
    ``fail_open=True``، بدونِ استثنا و با لاگِ خطا)."""
    key = build_key(action, identifier)
    window_seconds = int(window_seconds)
    if window_seconds < 1:
        raise ValueError("window_seconds must be >= 1 (0 would expire the counter immediately)")
    try:
        count = get_counter().hit(key, window_seconds)
    except Exception as exc:  # noqa: BLE001 — any backend failure must be classified
        # Class name only: connection errors can embed the (credentialed) URL.
        logger.error("Rate-limit backend failure for %s: %s", action, exc.__class__.__name__)
        if fail_open:
            return
        raise RateLimitUnavailable(UNAVAILABLE_MESSAGE) from exc
    if count > max_attempts:
        raise RateLimitExceeded(f"تعداد تلاش برای «{action}» بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید")
