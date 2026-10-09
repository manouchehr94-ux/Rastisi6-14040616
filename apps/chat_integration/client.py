"""Minimal RastiChat Integration Contract v1 client: Ed25519-signed short-lived JWTs + a few HTTPS calls.

Uses only libraries RastiSi already depends on (``cryptography`` for Ed25519, ``requests``). The private key never leaves
this process; RastiChat stores only the public key. A NEW token is minted for every request (also every retry): it lives
30 s, is single-use, and is bound to the method, path and body hash. Tokens/keys are never logged.
"""
import base64
import hashlib
import json
import logging
import time
import uuid

import requests
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django.conf import settings

from . import conf

logger = logging.getLogger(__name__)


class RastiChatError(Exception):
    """A RastiChat call failed. ``code`` is the contract's stable error code when RastiChat answered."""

    def __init__(self, message, *, status=None, code=""):
        super().__init__(message)
        self.status = status
        self.code = code


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_jwt(claims: dict) -> str:
    pem = conf.private_key_pem()
    if not pem:
        raise RastiChatError("RastiChat signing key is not configured.")
    header = _b64url(json.dumps({"alg": "EdDSA", "typ": "JWT", "kid": settings.RASTICHAT_KEY_ID}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    key = load_pem_private_key(pem.encode(), password=None)
    return f"{header}.{payload}.{_b64url(key.sign(f'{header}.{payload}'.encode()))}"


def _audience(purpose: str) -> str:
    return f"{getattr(settings, 'RASTICHAT_TOKEN_AUDIENCE', 'rastichat')}:{purpose}"


def make_assertion(*, actor: str, sub: str, tenant: str | None = None, role: str | None = None, name: str = "",
                   origin: str = "", ttl: int = 60) -> str:
    """An identity assertion for the BROWSER to relay (Contract v1 §7). Every claim must come from RastiSi's own
    server-side state — never from request parameters."""
    now = int(time.time())
    claims = {"iss": settings.RASTICHAT_INTEGRATION_SLUG, "aud": _audience("identity"), "sub": sub, "actor": actor,
              "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex}
    if tenant:
        claims["tenant"] = tenant
    if role:
        claims["role"] = role
    if name:
        claims["name"] = name[:255]
    if origin:
        claims["origin"] = origin
    return sign_jwt(claims)


def request(method: str, path: str, body: dict | None = None, *, idempotency_key: str | None = None, timeout=(3.05, 10)):
    raw = b"" if body is None else json.dumps(body, separators=(",", ":")).encode()
    now = int(time.time())
    token = sign_jwt({
        "iss": settings.RASTICHAT_INTEGRATION_SLUG, "sub": settings.RASTICHAT_INTEGRATION_SLUG, "aud": _audience("api"),
        "iat": now, "exp": now + 30, "jti": uuid.uuid4().hex, "htm": method, "htu": path,
        "bh": _b64url(hashlib.sha256(raw).digest()),
    })
    headers = {"Authorization": f"Bearer {token}"}
    if raw:
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        response = requests.request(method, settings.RASTICHAT_BASE_URL.rstrip("/") + path, data=raw or None,
                                    headers=headers, timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        # connection details only — never the token
        logger.warning("rastichat_unreachable method=%s path=%s error=%s", method, path, type(exc).__name__)
        raise RastiChatError("RastiChat is unreachable.") from exc
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400:
        err = (data.get("error") or {}) if isinstance(data, dict) else {}
        logger.warning("rastichat_error method=%s path=%s status=%s code=%s", method, path, response.status_code, err.get("code"))
        raise RastiChatError(err.get("message") or f"RastiChat answered {response.status_code}.",
                             status=response.status_code, code=err.get("code", ""))
    return data


# --- the handful of contract operations RastiSi uses ---
def ensure_tenant(external_tenant_id: str, payload: dict) -> dict:
    return request("PUT", f"/api/v1/integrations/tenants/{external_tenant_id}/", payload)


def set_tenant_status(external_tenant_id: str, status: str) -> dict:
    return request("PUT", f"/api/v1/integrations/tenants/{external_tenant_id}/", {"status": status})


def set_staff_member(external_tenant_id: str, user_id: str, role: str, display_name: str = "") -> dict:
    return request("PUT", f"/api/v1/integrations/tenants/{external_tenant_id}/members/{user_id}/",
                   {"role": role, "display_name": display_name})


def remove_staff_member(external_tenant_id: str, user_id: str) -> dict:
    return request("DELETE", f"/api/v1/integrations/tenants/{external_tenant_id}/members/{user_id}/")


def set_platform_member(user_id: str, role: str, display_name: str = "") -> dict:
    return request("PUT", f"/api/v1/integrations/platform/members/{user_id}/", {"role": role, "display_name": display_name})


def disable_staff_user(user_id: str) -> dict:
    return request("POST", f"/api/v1/integrations/users/{user_id}/disable/")


def start_support_conversation(external_tenant_id: str, *, initiator_user_id: str, subject: str, message: str,
                               subject_key: str, idempotency_key: str, client_message_id: str) -> dict:
    return request("POST", f"/api/v1/integrations/tenants/{external_tenant_id}/support-conversations/", {
        "initiator_user_id": initiator_user_id, "subject": subject, "subject_key": subject_key, "message": message,
        "client_message_id": client_message_id}, idempotency_key=idempotency_key)
