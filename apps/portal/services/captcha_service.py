"""Local ALTCHA PoW v2 for public authentication/contact forms.

Official altcha-django constructs/verifies the challenge. RastiSi keeps its own
shared-store fencing: expiry, exact issued challenge, session + action binding,
per-IP budgets and atomic one-use consumption (including invalid attempts).
No Cloudflare, ALTCHA Cloud, Sentinel or remote verification call is used.
"""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import time
from dataclasses import dataclass

from altcha_django.challenge import ChallengeConfig, build_challenge
from altcha_django.verifiers.local import LocalVerifier
from django.conf import settings
from django.core.cache import caches
from django.urls import reverse
from django.utils.crypto import salted_hmac

from apps.core.services.client_ip import get_client_ip_bucket
from apps.core.services.rate_limit import (
    UNAVAILABLE_MESSAGE,
    RateLimitExceeded,
    RateLimitUnavailable,
    enforce_rate_limit,
)

logger = logging.getLogger(__name__)
PAYLOAD_FIELD = "altcha"
ACTIONS = frozenset(
    {"login_password", "login_otp", "register", "password_reset", "contact"}
)
PUBLIC_ERROR_MESSAGE = (
    "تأیید امنیتی معتبر نیست یا منقضی شده است؛ دوباره «من ربات نیستم» را تأیید کنید."
)
RATE_LIMITED_MESSAGE = (
    "تعداد تلاش‌ها برای تأیید امنیتی بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید."
)
VERIFY_MAX_ATTEMPTS, VERIFY_WINDOW_SECONDS = 120, 600
ISSUE_MAX, ISSUE_WINDOW_SECONDS = 600, 600
MAX_PAYLOAD_CHARS = 4096
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_KEY_PREFIX = "captcha:altcha:v2:"


class CaptchaUnavailable(Exception):
    pass


@dataclass(frozen=True)
class CaptchaResult:
    success: bool
    error_code: str = ""
    message: str = ""
    skipped: bool = False


def _production():
    return bool(getattr(settings, "RASTISI_PRODUCTION_MODE", False))


def is_enabled():
    return bool(getattr(settings, "RASTISI_CAPTCHA_ENABLED", False))


def _ttl():
    return int(getattr(settings, "RASTISI_CAPTCHA_TTL_SECONDS", 300))


def _store():
    return caches[getattr(settings, "RASTISI_RATE_LIMIT_CACHE_ALIAS", "ratelimit")]


def _storage_key(nonce):
    return (
        _KEY_PREFIX
        + salted_hmac("rastisi.altcha.cache", nonce, algorithm="sha256").hexdigest()
    )


def _secret(purpose):
    return salted_hmac(
        "rastisi.altcha." + purpose, "pow-v2", algorithm="sha256"
    ).digest()


def _session_digest(session_key, action):
    return salted_hmac(
        "rastisi.altcha.session", f"{session_key}:{action}", algorithm="sha256"
    ).hexdigest()


def _challenge_digest(challenge):
    return hashlib.sha256(
        json.dumps(
            challenge, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _ensure_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def widget_config(request, action):
    """Render the checkbox immediately; issue PoW only when the visitor clicks.

    Establish the session on the page response (the two login widgets must share
    a stable cookie) and check the store without creating unused challenges.
    """
    if action not in ACTIONS:
        raise ValueError("unknown CAPTCHA action")
    if not is_enabled():
        return {"enabled": False}
    try:
        _ensure_session_key(request)
        _store().get(_KEY_PREFIX + "availability")
    except Exception as exc:
        logger.warning(
            "ALTCHA unavailable while rendering (%s)", exc.__class__.__name__
        )
        return {"enabled": True, "unavailable": True}
    return {
        "enabled": True,
        "unavailable": False,
        "challenge_url": reverse("portal:altcha-challenge", kwargs={"action": action}),
    }


def issue(request, action):
    if action not in ACTIONS:
        raise ValueError("unknown CAPTCHA action")
    if not is_enabled():
        return {"enabled": False}
    try:
        enforce_rate_limit(
            "captcha_issue",
            get_client_ip_bucket(request),
            max_attempts=ISSUE_MAX,
            window_seconds=ISSUE_WINDOW_SECONDS,
        )
        session_key = _ensure_session_key(request)
        config = ChallengeConfig(
            algorithm="PBKDF2/SHA-256",
            cost=getattr(settings, "RASTISI_ALTCHA_COST", 1000),
            max_number=getattr(settings, "RASTISI_ALTCHA_MAX_NUMBER", 128),
            key_length=32,
            expires_seconds=_ttl(),
        )
        challenge = build_challenge(
            config=config,
            hmac_secret=_secret("sign"),
            hmac_key_secret=_secret("key"),
            hmac_algorithm="SHA-256",
            data={"action": action},
            bind_session_token=False,
        ).to_dict()
        nonce = challenge["parameters"]["nonce"]
        record = {
            "s": _session_digest(session_key, action),
            "a": action,
            "t": int(time.time()),
            "c": _challenge_digest(challenge),
            "m": config.max_number,
        }
        _store().set(_storage_key(nonce), record, timeout=_ttl())
    except (RateLimitExceeded, RateLimitUnavailable) as exc:
        logger.warning("ALTCHA challenge unavailable (%s)", exc.__class__.__name__)
        return {
            "enabled": True,
            "unavailable": True,
            "rate_limited": isinstance(exc, RateLimitExceeded),
        }
    except Exception as exc:
        logger.error(
            "ALTCHA challenge could not be issued (%s)", exc.__class__.__name__
        )
        return {"enabled": True, "unavailable": True}
    return {
        "enabled": True,
        "unavailable": False,
        "challenge": challenge,
        "token": nonce,
    }


def _consume(nonce):
    """DEL is atomic on Redis; exactly one contender can win. Never reuse a nonce."""
    try:
        store, key = _store(), _storage_key(nonce)
        record = store.get(key)
        if record is None or not store.delete(key):
            return None
        return record
    except Exception as exc:
        logger.error("ALTCHA shared store unavailable (%s)", exc.__class__.__name__)
        raise CaptchaUnavailable from exc


def _unique_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate payload key")
        data[key] = value
    return data


def decode_payload(raw):
    """Bound decoding and reject duplicate keys, non-object JSON and test payloads."""
    if not isinstance(raw, str) or not raw or len(raw) > MAX_PAYLOAD_CHARS:
        return None
    try:
        data = json.loads(
            base64.b64decode(raw, validate=True),
            object_pairs_hook=_unique_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError("nonfinite JSON")
            ),
        )
        if not isinstance(data, dict) or set(data) != {"challenge", "solution"}:
            return None
        nonce = data["challenge"]["parameters"]["nonce"]
        if not isinstance(nonce, str) or not _NONCE_RE.fullmatch(nonce):
            return None
        return data
    except (
        ValueError,
        TypeError,
        KeyError,
        binascii.Error,
        UnicodeDecodeError,
        RecursionError,
    ):
        return None


def verify_request(request, *, action):
    if action not in ACTIONS:
        raise ValueError("unknown CAPTCHA action")
    if not is_enabled():
        if _production():
            return CaptchaResult(False, "captcha-misconfigured", UNAVAILABLE_MESSAGE)
        return CaptchaResult(True, skipped=True)
    try:
        enforce_rate_limit(
            "captcha_verify",
            get_client_ip_bucket(request),
            max_attempts=VERIFY_MAX_ATTEMPTS,
            window_seconds=VERIFY_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        return CaptchaResult(False, "rate-limited", RATE_LIMITED_MESSAGE)
    except RateLimitUnavailable:
        return CaptchaResult(False, "store-unavailable", UNAVAILABLE_MESSAGE)
    raw = request.POST.get(PAYLOAD_FIELD, "")
    decoded = decode_payload(raw)
    if decoded is None:
        return CaptchaResult(False, "invalid-payload", PUBLIC_ERROR_MESSAGE)
    try:
        record = _consume(decoded["challenge"]["parameters"]["nonce"])
    except CaptchaUnavailable:
        return CaptchaResult(False, "store-unavailable", UNAVAILABLE_MESSAGE)
    if not isinstance(record, dict):
        return CaptchaResult(False, "unknown-or-used-token", PUBLIC_ERROR_MESSAGE)
    issued = record.get("t")
    if type(issued) is not int or not 0 <= time.time() - issued <= _ttl():
        return CaptchaResult(False, "expired", PUBLIC_ERROR_MESSAGE)
    if record.get("a") != action:
        return CaptchaResult(False, "wrong-action", PUBLIC_ERROR_MESSAGE)
    session_key = getattr(request.session, "session_key", None)
    if not session_key or not hmac.compare_digest(
        str(record.get("s", "")), _session_digest(session_key, action)
    ):
        return CaptchaResult(False, "wrong-session", PUBLIC_ERROR_MESSAGE)
    try:
        if not hmac.compare_digest(
            _challenge_digest(decoded["challenge"]), str(record.get("c", ""))
        ):
            return CaptchaResult(False, "tampered-challenge", PUBLIC_ERROR_MESSAGE)
        solution = decoded["solution"]
        if not isinstance(solution, dict) or set(solution) - {
            "counter",
            "derivedKey",
            "time",
        }:
            return CaptchaResult(False, "invalid-solution", PUBLIC_ERROR_MESSAGE)
        counter, key = solution.get("counter"), solution.get("derivedKey")
        if (
            type(counter) is not int
            or not 0 <= counter < record["m"]
            or not isinstance(key, str)
            or not _KEY_RE.fullmatch(key)
        ):
            return CaptchaResult(False, "invalid-solution", PUBLIC_ERROR_MESSAGE)
        result = LocalVerifier(
            hmac_secret=_secret("sign"),
            hmac_key_secret=_secret("key"),
            hmac_algorithm="SHA-256",
            bind_session=False,
        ).verify(raw, request=request)
    except Exception as exc:
        logger.warning("ALTCHA payload rejected (%s)", exc.__class__.__name__)
        return CaptchaResult(False, "invalid-solution", PUBLIC_ERROR_MESSAGE)
    return (
        CaptchaResult(True)
        if result.verified
        else CaptchaResult(False, "invalid-solution", PUBLIC_ERROR_MESSAGE)
    )
