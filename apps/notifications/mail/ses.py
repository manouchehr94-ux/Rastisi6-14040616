"""Amazon SES (API v2 / ``sesv2``) adapter — production transport.

Reference: boto3 ``sesv2`` client — ``create_email_identity``, ``get_email_identity``, ``send_email``
(https://docs.aws.amazon.com/ses/latest/APIReference-V2/). Domain identities are verified by DKIM CNAME
records (Easy DKIM): ``CreateEmailIdentity`` on a bare domain returns ``DkimAttributes.Tokens``, each of which
becomes a CNAME record ``{token}._domainkey.{domain}`` → ``{token}.dkim.amazonses.com``
(https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dkim.html). ``GetEmailIdentity`` reports
``VerificationStatus`` (PENDING/SUCCESS/FAILED/TEMPORARY_FAILURE/NOT_STARTED) and ``VerifiedForSendingStatus``
(https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_GetEmailIdentity.html).

No boto3 client is constructed, and no network call is made, until a method is actually invoked — importing
this module must never require AWS credentials (keeps ``manage.py check``/tests clean when SES is unused)."""

from __future__ import annotations

import logging
import re

from django.conf import settings

from .base import (
    PROVIDER_FAILED, PROVIDER_NOT_FOUND, PROVIDER_PENDING, PROVIDER_TEMPORARY_FAILURE, PROVIDER_VERIFIED,
    DnsRecord, EmailTransport, IdentityState, OutboundEmail, SendOutcome, TransportNotConfigured,
)

logger = logging.getLogger(__name__)

_DKIM_CNAME_SUFFIX = "dkim.amazonses.com"

# SES VerificationStatus → our provider-neutral vocabulary
_STATUS_MAP = {
    "SUCCESS": PROVIDER_VERIFIED,
    "PENDING": PROVIDER_PENDING,
    "NOT_STARTED": PROVIDER_PENDING,
    "FAILED": PROVIDER_FAILED,
    "TEMPORARY_FAILURE": PROVIDER_TEMPORARY_FAILURE,
}

# Retryable SES error codes (throttling/transient) vs permanent (never retried as-is)
_RETRYABLE_CODES = {"Throttling", "ThrottlingException", "TooManyRequestsException", "ServiceUnavailable"}


class SesTransport(EmailTransport):
    code = "ses"

    def __init__(self, *, region: str | None = None, access_key: str | None = None, secret_key: str | None = None):
        self.region = region or getattr(settings, "RASTISI_SES_REGION", "")
        self.access_key = access_key or getattr(settings, "RASTISI_SES_ACCESS_KEY_ID", "")
        self.secret_key = secret_key or getattr(settings, "RASTISI_SES_SECRET_ACCESS_KEY", "")
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.region:
            raise TransportNotConfigured("RASTISI_SES_REGION تنظیم نشده است.")
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover — boto3 is an optional, SES-only dependency
            raise TransportNotConfigured("کتابخانه‌ی boto3 نصب نیست؛ اتصال واقعی به SES ممکن نیست.") from exc
        kwargs = {"region_name": self.region}
        if self.access_key and self.secret_key:
            kwargs["aws_access_key_id"] = self.access_key
            kwargs["aws_secret_access_key"] = self.secret_key
        # if no explicit keys: boto3 falls back to the instance/task role — the AWS-recommended, no-secret-in-repo path
        self._client = boto3.client("sesv2", **kwargs)
        return self._client

    # --- identity lifecycle -----------------------------------------------------------------------------
    def create_identity(self, domain: str) -> IdentityState:
        client = self._get_client()
        try:
            client.create_email_identity(EmailIdentity=domain)
        except client.exceptions.AlreadyExistsException:
            pass
        except client.exceptions.ClientError as exc:  # noqa: BLE001
            logger.warning("SES create_email_identity failed for a domain: %s", _safe(exc))
            return IdentityState(status=PROVIDER_TEMPORARY_FAILURE, detail="provider error")
        return self.get_identity(domain)

    def get_identity(self, domain: str) -> IdentityState:
        client = self._get_client()
        try:
            resp = client.get_email_identity(EmailIdentity=domain)
        except client.exceptions.NotFoundException:
            return IdentityState(status=PROVIDER_NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 — any other provider/network failure is "temporary", never "verified"
            logger.warning("SES get_email_identity failed for a domain: %s", _safe(exc))
            return IdentityState(status=PROVIDER_TEMPORARY_FAILURE, detail="provider error")

        dkim = resp.get("DkimAttributes") or {}
        tokens = dkim.get("Tokens") or []
        records = tuple(
            DnsRecord("CNAME", f"{token}._domainkey.{domain}", f"{token}.{_DKIM_CNAME_SUFFIX}", "dkim")
            for token in tokens
        )
        raw_status = dkim.get("Status") or resp.get("VerificationStatus") or "NOT_STARTED"
        status = _STATUS_MAP.get(raw_status, PROVIDER_PENDING)
        return IdentityState(
            status=status, verified_for_sending=bool(resp.get("VerifiedForSendingStatus")), dns_records=records,
            error_type=((resp.get("VerificationInfo") or {}).get("ErrorType") or ""),
            provider_ref=f"ses:{domain}",
        )

    # --- sending -----------------------------------------------------------------------------------------
    def send(self, message: OutboundEmail) -> SendOutcome:
        client = self._get_client()
        content = {
            "Simple": {
                "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": message.text_body, "Charset": "UTF-8"},
                    **({"Html": {"Data": message.html_body, "Charset": "UTF-8"}} if message.html_body else {}),
                },
            }
        }
        kwargs = dict(
            FromEmailAddress=f"{message.from_name} <{message.from_address}>" if message.from_name else message.from_address,
            Destination={"ToAddresses": [message.to_address]},
            Content=content,
        )
        if message.reply_to:
            kwargs["ReplyToAddresses"] = [message.reply_to]
        if message.tags:
            kwargs["EmailTags"] = [{"Name": k, "Value": str(v)} for k, v in message.tags.items()]
        try:
            resp = client.send_email(**kwargs)
        except Exception as exc:  # noqa: BLE001 — classify below, never raise into the caller
            response = getattr(exc, "response", None) or {}
            provider_code = response.get("Error", {}).get("Code", "")
            code = provider_code or type(exc).__name__
            # A provider verdict (an AWS error code) is permanent unless it is a throttling/availability code. An error
            # WITHOUT a provider verdict (timeout, connection reset, DNS failure…) says nothing about the message: retry.
            retryable = (provider_code in _RETRYABLE_CODES) if provider_code else True
            logger.warning("SES send_email failed (code=%s retryable=%s): %s", code, retryable, _safe(exc))
            return SendOutcome(False, error_code=code, error=_safe(exc), retryable=retryable)
        return SendOutcome(True, message_id=resp.get("MessageId", ""))


def _safe(exc: Exception) -> str:
    """Error text with no AWS key/secret, no full request payload — provider error class + short reason only."""
    text = re.sub(r"(AKIA|ASIA)[0-9A-Z]{16}", "[redacted-key]", str(exc))
    text = re.sub(r"(?i)(secret|token|password|signature)[=:\s]+\S+", r"\1=[redacted]", text)
    return f"{type(exc).__name__}: {text[:200]}"
