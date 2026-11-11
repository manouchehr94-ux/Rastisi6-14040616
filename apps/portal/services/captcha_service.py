"""Server-side math CAPTCHA for the public account and contact forms (replaces Cloudflare Turnstile).

The visitor sees a question such as «۳۵ + ۱۴ = ؟» and types the sum. Everything that matters happens on the server:

* **The answer never leaves the server.** The page carries only the two operands and a random, opaque token. The cache holds
  an HMAC of ``token:answer`` (keyed with ``SECRET_KEY``), not the answer. The token is random; it is not derived from the answer.
* **Bound to the session and to the form.** The stored challenge records an HMAC of the visitor's session key and the action
  (``login_password``, ``login_otp``, ``register``, ``password_reset``, ``contact``). A token issued to another session, or for
  another form, never verifies.
* **Short-lived.** The cache entry expires after ``RASTISI_CAPTCHA_TTL_SECONDS`` (default 300) and the issue time is checked again on use.
* **Single use, also under concurrency.** Every submission consumes the token *first*, whether the answer is right or wrong:
  ``cache.delete()`` returns ``True`` for exactly one caller, so two simultaneous requests with the same token cannot both pass.
  A wrong answer therefore costs the visitor a new question (one guess per question).
* **Budgets.** Each verification attempt spends one unit of a per-client-IP budget, and issuing questions is budgeted per IP as well
  (both in the shared rate-limit store). These are in addition to, not instead of, the existing per-endpoint limits.
* **Fail closed.** If the shared store (Redis in production) is unavailable, a question cannot be issued and a submission cannot be
  verified: the form is refused with the standard "temporarily unavailable" message. Production never treats "CAPTCHA off" as success.

Honest limit: a math question stops naive scripts, not a determined bot that parses the page. The real protection against
SMS pumping and password guessing stays the rate limits and per-identifier throttles that run after this check.
"""

import hmac
import logging
import re
import secrets
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import caches
from django.utils.crypto import salted_hmac

from apps.core.services.client_ip import get_client_ip_bucket
from apps.core.services.rate_limit import (
    UNAVAILABLE_MESSAGE,
    RateLimitExceeded,
    RateLimitUnavailable,
    enforce_rate_limit,
)

logger = logging.getLogger(__name__)

TOKEN_FIELD = "captcha_token"
ANSWER_FIELD = "captcha_answer"

ACTIONS = frozenset({"login_password", "login_otp", "register", "password_reset", "contact"})

PUBLIC_ERROR_MESSAGE = "پاسخ تأیید امنیتی درست نیست یا منقضی شده است؛ سؤال تازه را حل کنید."
RATE_LIMITED_MESSAGE = "تعداد تلاش‌ها برای تأیید امنیتی بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید."

#: Operands are two-digit numbers (10..49); the sum is 20..98.
OPERAND_MIN = 10
OPERAND_MAX = 49

#: Backstop budgets per client IP bucket (shared store): verification counts every attempt, issue counts every question shown.
#: Deliberately generous: mobile carriers put many real users behind one IP, and the strict limits (login 15, OTP 10, reset/contact 5 per
#: 10 minutes) live in the endpoints. These only stop flooding of the store and of the verifier.
VERIFY_MAX_ATTEMPTS = 120
VERIFY_WINDOW_SECONDS = 600
ISSUE_MAX = 600
ISSUE_WINDOW_SECONDS = 600

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_KEY_PREFIX = "captcha:v1:"
_SALT_ANSWER = "rastisi.captcha.answer"
_SALT_SESSION = "rastisi.captcha.session"
_MAX_ANSWER_CHARS = 12

# Persian (U+06F0..06F9) and Arabic-Indic (U+0660..0669) digits -> ASCII. Only whitespace and invisible bidi/joiner marks are
# dropped; no separator is accepted ("4,5" is not 45).
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})
_STRIP = dict.fromkeys(map(ord, " \t\r\n\u00a0\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u2066\u2067\u2068\u2069"))
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


class CaptchaUnavailable(Exception):
    """The shared store cannot be used; the caller must fail closed."""


@dataclass(frozen=True)
class CaptchaResult:
    success: bool
    error_code: str = ""
    message: str = ""
    skipped: bool = False


def _production() -> bool:
    return bool(getattr(settings, "RASTISI_PRODUCTION_MODE", False))


def is_enabled() -> bool:
    return bool(getattr(settings, "RASTISI_CAPTCHA_ENABLED", False))


def _ttl() -> int:
    return int(getattr(settings, "RASTISI_CAPTCHA_TTL_SECONDS", 300))


def _store():
    return caches[getattr(settings, "RASTISI_RATE_LIMIT_CACHE_ALIAS", "ratelimit")]


def _storage_key(token: str) -> str:
    return _KEY_PREFIX + salted_hmac("rastisi.captcha.key", token).hexdigest()


def _answer_digest(token: str, answer: int) -> str:
    return salted_hmac(_SALT_ANSWER, f"{token}:{answer}").hexdigest()


def _session_digest(session_key: str, action: str) -> str:
    return salted_hmac(_SALT_SESSION, f"{session_key}:{action}").hexdigest()


def normalize_answer(raw) -> int | None:
    """Persian, Arabic-Indic and ASCII digits are all accepted. Anything else (signs, letters, decimals, empty) is rejected."""
    text = str(raw or "")
    if len(text) > _MAX_ANSWER_CHARS:
        return None
    text = text.translate(_DIGIT_MAP).translate(_STRIP)
    if not text or not text.isascii() or not text.isdigit() or len(text) > 3:
        return None
    return int(text)


def to_persian_digits(value) -> str:
    return str(value).translate(_PERSIAN_DIGITS)


def _ensure_session_key(request) -> str:
    session = request.session
    if not session.session_key:
        session.create()
    return session.session_key


def issue(request, action: str) -> dict:
    """Create a challenge for ``action`` and return what the template may show.

    Returns ``{"enabled": False}`` when the CAPTCHA is off (development only), ``{"enabled": True, "unavailable": True}`` when the shared
    store cannot be used (the form then cannot be submitted successfully), or the question with its opaque token. The answer is never returned.
    """
    if action not in ACTIONS:
        raise ValueError("unknown CAPTCHA action")
    if not is_enabled():
        return {"enabled": False}
    try:
        enforce_rate_limit(
            "captcha_issue", get_client_ip_bucket(request), max_attempts=ISSUE_MAX, window_seconds=ISSUE_WINDOW_SECONDS,
        )
        session_key = _ensure_session_key(request)
        a = OPERAND_MIN + secrets.randbelow(OPERAND_MAX - OPERAND_MIN + 1)
        b = OPERAND_MIN + secrets.randbelow(OPERAND_MAX - OPERAND_MIN + 1)
        token = secrets.token_urlsafe(24)
        payload = {
            "h": _answer_digest(token, a + b),
            "s": _session_digest(session_key, action),
            "a": action,
            "t": int(time.time()),
        }
        _store().set(_storage_key(token), payload, timeout=_ttl())
    except (RateLimitExceeded, RateLimitUnavailable) as exc:
        logger.warning("CAPTCHA question could not be issued: %s", exc.__class__.__name__)
        return {"enabled": True, "unavailable": True}
    except Exception as exc:  # noqa: BLE001 — a cache/session failure must never become a 500 on a public page
        logger.error("CAPTCHA store failure while issuing: %s", exc.__class__.__name__)
        return {"enabled": True, "unavailable": True}
    return {
        "enabled": True,
        "unavailable": False,
        "token": token,
        "left": to_persian_digits(a),
        "right": to_persian_digits(b),
        "token_field": TOKEN_FIELD,
        "answer_field": ANSWER_FIELD,
        "ttl_minutes": to_persian_digits(max(1, _ttl() // 60)),
    }


def _consume(token: str):
    """Atomically take the challenge out of the store. Exactly one caller gets it; the others get ``None``."""
    try:
        store = _store()
        key = _storage_key(token)
        payload = store.get(key)
        if payload is None:
            return None
        if not store.delete(key):          # somebody else consumed it between get() and delete()
            return None
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.error("CAPTCHA store failure while verifying: %s", exc.__class__.__name__)
        raise CaptchaUnavailable from exc


def verify_request(request, *, action: str) -> CaptchaResult:
    """Check the submitted answer for ``action``. Consumes the token whatever the outcome."""
    if action not in ACTIONS:
        raise ValueError("unknown CAPTCHA action")
    if not is_enabled():
        if _production():
            # Defence in depth behind the startup/system-check enforcement: production never treats "CAPTCHA off" as success.
            logger.error("CAPTCHA is disabled in production configuration; failing closed.")
            return CaptchaResult(False, "captcha-misconfigured", UNAVAILABLE_MESSAGE)
        return CaptchaResult(True, skipped=True)

    try:
        enforce_rate_limit(
            "captcha_verify", get_client_ip_bucket(request),
            max_attempts=VERIFY_MAX_ATTEMPTS, window_seconds=VERIFY_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        return CaptchaResult(False, "rate-limited", RATE_LIMITED_MESSAGE)
    except RateLimitUnavailable:
        return CaptchaResult(False, "store-unavailable", UNAVAILABLE_MESSAGE)

    token = str(request.POST.get(TOKEN_FIELD, "") or "")
    answer = normalize_answer(request.POST.get(ANSWER_FIELD, ""))
    if not _TOKEN_RE.match(token):
        return CaptchaResult(False, "missing-token", PUBLIC_ERROR_MESSAGE)

    try:
        payload = _consume(token)           # single use: burned even when the answer below is wrong
    except CaptchaUnavailable:
        return CaptchaResult(False, "store-unavailable", UNAVAILABLE_MESSAGE)
    if not isinstance(payload, dict):
        return CaptchaResult(False, "unknown-or-used-token", PUBLIC_ERROR_MESSAGE)

    issued_at = payload.get("t")
    if not isinstance(issued_at, int) or not (0 <= time.time() - issued_at <= _ttl()):
        return CaptchaResult(False, "expired", PUBLIC_ERROR_MESSAGE)
    if payload.get("a") != action:
        return CaptchaResult(False, "wrong-action", PUBLIC_ERROR_MESSAGE)
    session_key = getattr(request.session, "session_key", None)
    if not session_key or not hmac.compare_digest(str(payload.get("s", "")), _session_digest(session_key, action)):
        return CaptchaResult(False, "wrong-session", PUBLIC_ERROR_MESSAGE)
    if answer is None:
        return CaptchaResult(False, "missing-answer", PUBLIC_ERROR_MESSAGE)
    if not hmac.compare_digest(str(payload.get("h", "")), _answer_digest(token, answer)):
        return CaptchaResult(False, "wrong-answer", PUBLIC_ERROR_MESSAGE)
    return CaptchaResult(True)
