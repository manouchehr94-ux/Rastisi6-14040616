"""Cloudflare Turnstile server-side validation."""

from dataclasses import dataclass
import logging

import requests
from django.conf import settings

from apps.core.services.client_ip import get_client_ip

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
RESPONSE_FIELD = "cf-turnstile-response"
MAX_TOKEN_LENGTH = 2048
PUBLIC_ERROR_MESSAGE = "تأیید امنیتی ناموفق بود؛ لطفاً دوباره تلاش کنید."


@dataclass(frozen=True)
class TurnstileValidationResult:
    success: bool
    error_code: str = ""
    hostname: str = ""
    action: str = ""
    skipped: bool = False


def _normalized_hostname(value: str) -> str:
    return str(value or "").strip().lower().rstrip(".")


def verify_token(*, token: str, remote_ip: str = "", expected_action: str = ""):
    production = bool(getattr(settings, "RASTISI_PRODUCTION_MODE", False))
    if not getattr(settings, "TURNSTILE_ENABLED", False):
        if production:
            # Defence in depth behind the startup/system-check enforcement: a
            # production process can never treat "Turnstile off" as success.
            logger.error("Turnstile is disabled in production configuration; failing closed.")
            return TurnstileValidationResult(False, "turnstile-misconfigured")
        return TurnstileValidationResult(success=True, skipped=True)

    token = str(token or "").strip()
    if not token:
        return TurnstileValidationResult(False, "missing-token")
    if len(token) > MAX_TOKEN_LENGTH:
        return TurnstileValidationResult(False, "token-too-long")

    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = str(remote_ip)

    try:
        response = requests.post(
            SITEVERIFY_URL,
            data=payload,
            timeout=max(
                1,
                int(getattr(settings, "TURNSTILE_VERIFY_TIMEOUT_SECONDS", 5)),
            ),
        )
        response.raise_for_status()
        result = response.json()
    except Exception as exc:  # noqa: BLE001 — any provider/transport failure fails closed
        logger.warning(
            "Turnstile Siteverify request failed: %s",
            exc.__class__.__name__,
        )
        return TurnstileValidationResult(False, "siteverify-unavailable")

    if not isinstance(result, dict):
        return TurnstileValidationResult(False, "invalid-siteverify-response")

    if not bool(result.get("success")):
        codes = result.get("error-codes")
        code = str(codes[0]) if isinstance(codes, list) and codes else "verification-failed"
        return TurnstileValidationResult(False, code)

    action = str(result.get("action") or "")
    hostname = _normalized_hostname(result.get("hostname"))

    if expected_action and action != expected_action:
        return TurnstileValidationResult(
            False, "action-mismatch", hostname=hostname, action=action
        )

    expected_hostnames = {
        _normalized_hostname(value)
        for value in getattr(settings, "TURNSTILE_EXPECTED_HOSTNAMES", ())
        if _normalized_hostname(value)
    }
    if production and not expected_hostnames:
        logger.error("Turnstile expected hostnames are empty in production; failing closed.")
        return TurnstileValidationResult(
            False, "hostname-not-configured", hostname=hostname, action=action
        )
    if expected_hostnames and hostname not in expected_hostnames:
        return TurnstileValidationResult(
            False, "hostname-mismatch", hostname=hostname, action=action
        )

    return TurnstileValidationResult(
        True, hostname=hostname, action=action
    )


def verify_request(request, *, expected_action: str):
    return verify_token(
        token=request.POST.get(RESPONSE_FIELD, ""),
        remote_ip=get_client_ip(request),
        expected_action=expected_action,
    )
