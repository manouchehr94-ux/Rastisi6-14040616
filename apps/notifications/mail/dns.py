"""Authorized automatic DNS provisioning (optional).

RastiSi can only write DNS for a zone it is *authorized* to control (e.g. the merchant delegated the zone to a DNS
host RastiSi holds an API token for). That authorization is deployment-specific and platform-only, so this module
is an interface: ``RASTISI_EMAIL_DNS_PROVISIONER`` names a class implementing :class:`DnsProvisioner`. With none
configured (the default) every domain is "manual DNS" and the Store panel shows the exact records to add.

A provisioner must be conservative: return ``False`` (not raise) when it does not control the zone."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class DnsProvisioner(ABC):
    @abstractmethod
    def controls_zone(self, domain: str) -> bool:
        """True only if this deployment holds authorization to write records for ``domain``."""

    @abstractmethod
    def apply(self, domain: str, records) -> bool:
        """Create the given records. Return True only if every record was created/already present."""


class FakeDnsProvisioner(DnsProvisioner):
    """Test double: controls only the domains listed in ``zones``; records what it 'wrote' in ``applied``."""

    zones: set = set()
    applied: list = []

    @classmethod
    def reset(cls) -> None:
        cls.zones = set()
        cls.applied = []

    def controls_zone(self, domain: str) -> bool:
        return domain in self.zones

    def apply(self, domain: str, records) -> bool:
        self.applied.append((domain, [r.as_dict() for r in records]))
        return True


def get_provisioner() -> DnsProvisioner | None:
    path = getattr(settings, "RASTISI_EMAIL_DNS_PROVISIONER", "")
    if not path:
        return None
    return import_string(path)()


def try_apply(domain: str, records) -> bool:
    """Best-effort; never raises. ``False`` means "the merchant must add the records manually"."""
    try:
        provisioner = get_provisioner()
        if provisioner is None or not provisioner.controls_zone(domain):
            return False
        return bool(provisioner.apply(domain, records))
    except Exception:  # noqa: BLE001
        logger.exception("automatic DNS provisioning failed for a domain; falling back to manual records")
        return False


def annotate_published(domain: str, records: list, *, enabled: bool) -> list:
    """Adds ``published`` (True/False/None=unknown) to each record dict by a real DNS lookup. This is observation
    only — it never changes a status; ACTIVE still requires the email provider's own confirmation."""
    if not enabled:
        return [{**r, "published": None} for r in records]
    out = []
    for r in records:
        out.append({**r, "published": _lookup(r)})
    return out


def _lookup(record: dict):
    try:
        import dns.exception
        import dns.resolver

        answers = dns.resolver.resolve(record["name"], record["type"], lifetime=3)
        wanted = record["value"].strip().lower().rstrip(".")
        for rdata in answers:
            got = str(getattr(rdata, "target", rdata)).strip().lower().rstrip(".").strip('"')
            if got == wanted:
                return True
        return False
    except dns.resolver.NXDOMAIN:
        return False
    except Exception:  # noqa: BLE001 — timeouts/no network: unknown, never "published"
        return None
