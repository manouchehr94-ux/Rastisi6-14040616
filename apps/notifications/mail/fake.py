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
import json
import os
import re
import time
from pathlib import Path

from .base import (
    PROVIDER_FAILED, PROVIDER_NOT_FOUND, PROVIDER_PENDING, PROVIDER_TEMPORARY_FAILURE, PROVIDER_VERIFIED,
    DnsRecord, EmailTransport, IdentityState, OutboundEmail, SendOutcome,
)

_counter = itertools.count(1)

#: QA only. When set, identity state is shared between processes (web server, workers, QA CLI) through this JSON file and
#: every accepted message is written as a readable .html/.txt/.json trio into ``RASTISI_FAKE_EMAIL_MAILBOX_DIR``.
#: Only ever honoured by the fake provider; the QA tooling sets it, production never does.
STATE_FILE_ENV = "RASTISI_FAKE_EMAIL_STATE_FILE"
MAILBOX_DIR_ENV = "RASTISI_FAKE_EMAIL_MAILBOX_DIR"


def _state_path() -> Path | None:
    value = os.environ.get(STATE_FILE_ENV, "").strip()
    return Path(value) if value else None


def _load_shared() -> None:
    path = _state_path()
    if path and path.exists():
        try:
            FakeTransport.identities = json.loads(path.read_text(encoding="utf-8")).get("identities", {})
        except (OSError, ValueError):
            pass


def _save_shared() -> None:
    path = _state_path()
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"identities": FakeTransport.identities}, indent=1), encoding="utf-8")
        os.replace(tmp, path)


def _write_mailbox(mid: str, message) -> None:
    folder = os.environ.get(MAILBOX_DIR_ENV, "").strip()
    if not folder:
        return
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", mid)
    meta = {
        "message_id": mid, "from": f"{message.from_name} <{message.from_address}>", "from_address": message.from_address,
        "to": message.to_address, "subject": message.subject, "reply_to": message.reply_to, "headers": dict(message.headers),
        "tags": dict(message.tags), "sent_at_epoch": int(time.time()),
    }
    (root / f"{safe}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (root / f"{safe}.txt").write_text(message.text_body or "", encoding="utf-8")
    if message.html_body:
        (root / f"{safe}.html").write_text(message.html_body, encoding="utf-8")


class FakeTransport(EmailTransport):
    code = "fake"

    identities: dict = {}
    sent: list = []
    next_send_failures: list = []

    @classmethod
    def reset(cls) -> None:
        path = _state_path()
        if path and path.exists():
            path.unlink()
        cls.identities = {}
        cls.sent = []
        cls.next_send_failures = []

    # --- test controls ---------------------------------------------------------------------------------
    @classmethod
    def verify(cls, domain: str) -> None:
        _load_shared()
        cls.identities.setdefault(domain, {})["status"] = PROVIDER_VERIFIED
        _save_shared()

    @classmethod
    def fail_domain(cls, domain: str) -> None:
        _load_shared()
        cls.identities.setdefault(domain, {})["status"] = PROVIDER_FAILED
        _save_shared()

    @classmethod
    def temp_fail_domain(cls, domain: str) -> None:
        _load_shared()
        cls.identities.setdefault(domain, {})["status"] = PROVIDER_TEMPORARY_FAILURE
        _save_shared()

    # --- contract --------------------------------------------------------------------------------------
    @staticmethod
    def _records(domain: str) -> tuple:
        tokens = [hashlib.sha1(f"{domain}:{i}".encode()).hexdigest()[:20] for i in range(3)]  # noqa: S324 — fake tokens
        return tuple(DnsRecord("CNAME", f"{t}._domainkey.{domain}", f"{t}.dkim.fake-mail.test", "dkim") for t in tokens)

    def create_identity(self, domain: str) -> IdentityState:
        _load_shared()
        entry = self.identities.setdefault(domain, {})
        entry.setdefault("status", PROVIDER_PENDING)
        _save_shared()
        return self._state(domain)

    def get_identity(self, domain: str) -> IdentityState:
        _load_shared()
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
        _load_shared()
        domain = message.from_address.rsplit("@", 1)[-1].lower()
        entry = self.identities.get(domain)
        if not entry or entry.get("status") != PROVIDER_VERIFIED:
            # a real provider refuses an unverified sender; the fake must as well
            return SendOutcome(False, error_code="MessageRejected", error="sender identity not verified", retryable=False)
        mid = f"fake-{next(_counter):08d}" if not _state_path() else f"fake-{int(time.time() * 1000):013d}-{next(_counter):04d}"
        self.sent.append({"id": mid, "message": message})
        _write_mailbox(mid, message)
        return SendOutcome(True, message_id=mid)
