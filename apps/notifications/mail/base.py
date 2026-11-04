"""Transport contract. A transport NEVER raises for provider-level problems: it returns a typed result so the
caller can classify retryable vs permanent. Secrets must never appear in ``error`` strings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# --- identity verification states reported by a provider (provider-neutral vocabulary) -----------------------
PROVIDER_PENDING = "pending"
PROVIDER_VERIFIED = "verified"
PROVIDER_FAILED = "failed"
PROVIDER_TEMPORARY_FAILURE = "temporary_failure"
PROVIDER_NOT_FOUND = "not_found"


@dataclass(frozen=True)
class OutboundEmail:
    from_address: str
    from_name: str
    to_address: str
    subject: str
    text_body: str
    html_body: str = ""
    reply_to: str = ""
    headers: dict = field(default_factory=dict)
    #: opaque tags echoed back in provider events (never PII, never secrets)
    tags: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SendOutcome:
    ok: bool
    message_id: str = ""
    error_code: str = ""
    error: str = ""
    #: only meaningful when ``ok`` is False
    retryable: bool = True


@dataclass(frozen=True)
class DnsRecord:
    type: str      # CNAME / TXT / MX
    name: str
    value: str
    purpose: str   # dkim / spf / verification / dmarc / mail_from

    def as_dict(self) -> dict:
        return {"type": self.type, "name": self.name, "value": self.value, "purpose": self.purpose}


@dataclass(frozen=True)
class IdentityState:
    status: str                         # one of PROVIDER_*
    verified_for_sending: bool = False
    dns_records: tuple = ()             # tuple[DnsRecord, ...]
    error_type: str = ""
    provider_ref: str = ""
    detail: str = ""


class EmailTransport(ABC):
    code = ""

    @abstractmethod
    def create_identity(self, domain: str) -> IdentityState:
        """Create (idempotently) a domain identity and return its DNS records."""

    @abstractmethod
    def get_identity(self, domain: str) -> IdentityState:
        """Current verification state; ``PROVIDER_NOT_FOUND`` when the provider does not know the domain."""

    @abstractmethod
    def send(self, message: OutboundEmail) -> SendOutcome:
        """Send one message. Must not raise for provider errors."""


class TransportNotConfigured(Exception):
    """No usable provider is configured on this deployment (platform-only activation step)."""
