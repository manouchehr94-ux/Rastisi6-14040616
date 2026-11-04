"""Amazon SNS HTTP(S) notification authenticity check (used by the SES bounce/complaint/delivery webhook).

Implements the documented procedure (https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message-verify-message-signature.html):
the string to sign is built from a fixed, byte-sorted set of fields (``Key\\nValue\\n`` each, one trailing newline),
the signature is verified with the public key of the certificate at ``SigningCertURL`` — which MUST be an
https ``sns.<region>.amazonaws.com`` URL — using SHA1 (SignatureVersion 1) or SHA256 (SignatureVersion 2).
Additionally the TopicArn must be on our allowlist, so a validly-signed message from SOMEONE ELSE'S topic is refused."""

from __future__ import annotations

import base64
import re
from urllib.parse import urlparse

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings

_CERT_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$")
_NOTIFICATION_FIELDS = ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type")
_SUBSCRIPTION_FIELDS = ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type")


class SnsVerificationError(Exception):
    pass


def _fetch_certificate_pem(url: str) -> bytes:
    import requests

    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return response.content


def string_to_sign(payload: dict) -> str:
    kind = payload.get("Type")
    if kind == "Notification":
        fields = _NOTIFICATION_FIELDS
    elif kind in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        fields = _SUBSCRIPTION_FIELDS
    else:
        raise SnsVerificationError("unsupported message type")
    parts = []
    for name in fields:
        if name == "Subject" and "Subject" not in payload:
            continue  # optional: included only when present
        if name not in payload:
            raise SnsVerificationError(f"missing field {name}")
        parts.append(f"{name}\n{payload[name]}\n")
    return "".join(parts)


def verify_sns_message(payload: dict, *, cert_fetcher=None, allowed_topics=None) -> None:
    """Raises :class:`SnsVerificationError` unless the message is authentic AND from an allowlisted topic."""
    allowed = settings.RASTISI_SES_SNS_TOPIC_ARNS if allowed_topics is None else allowed_topics
    if not allowed or payload.get("TopicArn") not in allowed:
        raise SnsVerificationError("topic not allowed")
    url = payload.get("SigningCertURL") or ""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not _CERT_HOST.match(parsed.hostname or "") or parsed.port not in (None, 443):
        raise SnsVerificationError("untrusted signing certificate url")
    version = str(payload.get("SignatureVersion", ""))
    if version == "1":
        algorithm = hashes.SHA1()  # noqa: S303 — mandated by SNS SignatureVersion 1
    elif version == "2":
        algorithm = hashes.SHA256()
    else:
        raise SnsVerificationError("unsupported signature version")
    try:
        pem = (cert_fetcher or _fetch_certificate_pem)(url)
        public_key = x509.load_pem_x509_certificate(pem).public_key()
        signature = base64.b64decode(payload.get("Signature", ""), validate=True)
        public_key.verify(signature, string_to_sign(payload).encode("utf-8"), padding.PKCS1v15(), algorithm)
    except SnsVerificationError:
        raise
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise SnsVerificationError("signature mismatch") from exc
    except Exception as exc:  # noqa: BLE001 — network/cert problems: fail CLOSED
        raise SnsVerificationError("could not verify signature") from exc
