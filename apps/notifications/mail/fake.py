"""Deterministic in-memory provider for development and automated tests. NEVER contacts any network.

Behaviour is driven from tests through class-level knobs:

* ``verify(domain)``          — the (simulated) DNS records were seen: the identity becomes verified;
* ``fail_domain(domain)``     — verification fails permanently;
* ``temp_fail_domain(domain)``— provider temporary failure while checking;
* ``next_send_failures``      — queue of ``SendOutcome`` to return (consumed one per send) before success;
* ``sent``                    — every message accepted (inspect envelope/headers/body).
"""

from __future__ import annotations

import hashlib
import itertools

from .base import (
    PROVIDER_FAILED, PROVIDER_NOT_FOUND, PROVIDER_PENDING, PROVIDER_TEMPORARY_FAILURE, PROVIDER_VERIFIED,
    DnsRecord, EmailTransport, IdentityState, OutboundEmail, SendOutcome,
)

_counter = itertools.count(1)


class FakeTransport(EmailTransport):
    code = "fake"

    identities: dict = {}
    sent: list = []
    next_send_failures: list = []

    @classmethod
    def reset(cls) -> None:
        cls.identities = {}
        cls.sent = []
        cls.next_send_failures = []

    # --- test controls ---------------------------------------------------------------------------------
    @classmethod
    def verify(cls, domain: str) -> None:
        cls.identities.setdefault(domain, {})["status"] = PROVIDER_VERIFIED

    @classmethod
    def fail_domain(cls, domain: str) -> None:
        cls.identities.setdefault(domain, {})["status"] = PROVIDER_FAILED

    @classmethod
    def temp_fail_domain(cls, domain: str) -> None:
        cls.identities.setdefault(domain, {})["status"] = PROVIDER_TEMPORARY_FAILURE

    # --- contract --------------------------------------------------------------------------------------
    @staticmethod
    def _records(domain: str) -> tuple:
        tokens = [hashlib.sha1(f"{domain}:{i}".encode()).hexdigest()[:20] for i in range(3)]  # noqa: S324 — fake tokens
        return tuple(DnsRecord("CNAME", f"{t}._domainkey.{domain}", f"{t}.dkim.fake-mail.test", "dkim") for t in tokens)

    def create_identity(self, domain: str) -> IdentityState:
        entry = self.identities.setdefault(domain, {})
        entry.setdefault("status", PROVIDER_PENDING)
        return self._state(domain)

    def get_identity(self, domain: str) -> IdentityState:
        if domain not in self.identities:
            return IdentityState(status=PROVIDER_NOT_FOUND)
        return self._state(domain)

    def _state(self, domain: str) -> IdentityState:
        status = self.identities[domain]["status"]
        return IdentityState(
            status=status, verified_for_sending=(status == PROVIDER_VERIFIED), dns_records=self._records(domain),
            provider_ref=f"fake:{domain}", error_type="DNS_RECORDS_NOT_FOUND" if status == PROVIDER_FAILED else "",
        )

    def send(self, message: OutboundEmail) -> SendOutcome:
        if self.next_send_failures:
            return self.next_send_failures.pop(0)
        domain = message.from_address.rsplit("@", 1)[-1].lower()
        entry = self.identities.get(domain)
        if not entry or entry.get("status") != PROVIDER_VERIFIED:
            # a real provider refuses an unverified sender; the fake must as well
            return SendOutcome(False, error_code="MessageRejected", error="sender identity not verified", retryable=False)
        mid = f"fake-{next(_counter):08d}"
        self.sent.append({"id": mid, "message": message})
        return SendOutcome(True, message_id=mid)
