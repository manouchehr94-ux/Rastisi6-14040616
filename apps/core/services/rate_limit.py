"""محدودیت نرخ مبتنی‌بر cache — برای فرم‌های عمومیِ سایت (ثبت‌نام، ورود،
درخواستِ OTP، فرم تماس) و چند سقفِ per-Store.

در ``apps.core`` است (نه ``apps.portal``) چون مصرف‌کننده‌هایش هم لایه‌ی
پلتفرم‌اند (``apps.portal.services.owner_otp_service``) هم لایه‌ی
مستأجر/فروشگاه (``apps.sms.services.otp_service``) — و ``apps.sms`` نباید
به‌عقب به ``apps.portal`` وابسته شود.

**الگوریتم: پنجره‌ی ثابتِ (fixed window) متکی‌بر TTL، کاملاً اتمیک.**

* اولین فراخوان کلید را با ``cache.add(key, 1, timeout=window)`` می‌سازد
  (Redis: ``SET key 1 EX window NX`` — اتمیک؛ فقط یک worker برنده است).
* فراخوان‌هایِ بعدی ``cache.incr`` می‌زنند (Redis: ``INCR`` — اتمیک؛ هیچ
  read-modify-write ای در برنامه نیست). پنجره از *اولین* تلاش شروع می‌شود و
  TTLِ Redis تنها مرجعِ پایانِ آن است (وابسته به ساعتِ worker ها نیست).
* اگر کلید بینِ ``add`` و ``incr`` منقضی شود (``ValueError``) دوباره از
  ``add`` شروع می‌شود. اگر کلید بینِ ``EXISTS`` و ``INCR``ِ داخلیِ جنگو
  منقضی شود، ``INCR`` کلیدِ بدونِ TTL می‌سازد (مقدار ۱) — بلافاصله
  ``touch`` TTL را برمی‌گرداند تا شمارنده هرگز دائمی نشود.
* کلید: ``rl:v1:<action>:<sha256(identifier)[:32]>`` — نسخه برایِ تغییرِ
  فرمت در آینده؛ شناسه *همیشه* هش می‌شود پس ایمیل/توکن/کدِ خام هرگز در Redis
  نمی‌نشیند.

**سیاستِ قطعیِ backend (fail-closed):** هر خطایِ cache ``RateLimitUnavailable``
می‌دهد و فراخوان *نباید* ادامه دهد (ورودِ رمزی/ارسالِ OTP/ایمیلِ بازیابی
انجام نمی‌شود)، نه اینکه محدودیت بی‌صدا برداشته شود. استثنا: فراخوان‌هایِ
احرازشده‌یِ per-Store (سازنده‌ی فروشگاه) با ``fail_open=True`` صراحتاً اعلام
می‌کنند که این سقف مرزِ امنیتی نیست و قطعیِ Redis نباید پنل را از کار بیندازد."""

import hashlib
import logging
import re

from django.conf import settings
from django.core.cache import caches

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


def _store():
    return caches[getattr(settings, "RASTISI_RATE_LIMIT_CACHE_ALIAS", "ratelimit")]


def build_key(action: str, identifier) -> str:
    if not _ACTION_RE.match(action or ""):
        raise ValueError("rate-limit action must be a short [A-Za-z0-9_.:-] token")
    digest = hashlib.sha256(str(identifier).encode("utf-8")).hexdigest()[:32]
    return f"rl:{_KEY_VERSION}:{action}:{digest}"


def _increment(store, key: str, window_seconds: int) -> int:
    for _ in range(_MAX_ATTEMPTS):
        if store.add(key, 1, timeout=window_seconds):
            return 1
        try:
            count = store.incr(key)
        except ValueError:
            continue  # expired between add() and incr(): start the window again
        if count == 1:
            # INCR re-created an expired key without a TTL; make it expire.
            store.touch(key, window_seconds)
        return count
    raise RateLimitUnavailable("rate-limit counter did not stabilise")


def enforce_rate_limit(
    action: str, identifier: str, *, max_attempts: int, window_seconds: int, fail_open: bool = False,
) -> None:
    """اگر تعداد فراخوانی‌هایِ ``action``+``identifier`` در پنجره‌ی جاری از
    ``max_attempts`` بیشتر شود ``RateLimitExceeded`` می‌دهد؛ وگرنه شمارنده را
    اتمیک یکی افزایش می‌دهد. خطایِ backend → ``RateLimitUnavailable`` (یا، فقط با
    ``fail_open=True``، بدونِ استثنا و با لاگِ خطا)."""
    key = build_key(action, identifier)
    try:
        count = _increment(_store(), key, window_seconds)
    except Exception as exc:  # noqa: BLE001 — any backend failure must be classified
        # Class name only: connection errors can embed the (credentialed) URL.
        logger.error("Rate-limit backend failure for %s: %s", action, exc.__class__.__name__)
        if fail_open:
            return
        raise RateLimitUnavailable(UNAVAILABLE_MESSAGE) from exc
    if count > max_attempts:
        raise RateLimitExceeded(f"تعداد تلاش برای «{action}» بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید")
