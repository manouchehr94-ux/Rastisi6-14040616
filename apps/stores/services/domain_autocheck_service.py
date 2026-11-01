"""Periodic re-checking of a seller's custom domain, so nobody has to press «check» again and again while DNS propagates.

Only READING is automated. For every custom domain of ONE store this runs, at most at a bounded rate, the SAME checks the seller's «بررسی وضعیت» button runs:

* ownership (TXT) for a PENDING domain that asked for verification recently  → ``check_dns_verification`` (sets VERIFIED only when the real TXT record is found; otherwise changes nothing);
* routing + HTTPS readiness for a VERIFIED domain whose last check is stale     → ``refresh_custom_domain_readiness`` (persists routing / TLS status only).

It NEVER activates a domain (``activate_custom_domain`` and its SMS Step-Up stay the seller's final, deliberate act), never changes DNS records or certificates, and never contacts a DNS provider
or a certificate authority — the checks are the project's existing read-only lookups. The pass is off unless the platform owner enables ``RASTISI_DOMAIN_AUTOCHECK_ENABLED`` (default OFF) and runs
on the shared automation engine (store-scoped, de-duplicated, bounded, recorded only when something changed or failed)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core import automation
from apps.stores.models import StoreDomain
from apps.stores.services import domain_verification_service as dvs

OPERATION = "domain_recheck"
PENDING_WINDOW = timedelta(days=14)          # stop chasing an abandoned request
READINESS_STALE = timedelta(hours=6)         # not yet active: look again after this long
ACTIVE_STALE = timedelta(hours=24)           # already the primary domain: a daily health look


def enabled() -> bool:
    return bool(getattr(settings, "RASTISI_DOMAIN_AUTOCHECK_ENABLED", False))


def due(store, now=None) -> list[tuple[StoreDomain, str]]:
    """Which custom domains of THIS store are due, and for which check (``verify`` or ``readiness``)."""
    now = now or timezone.now()
    out = []
    for domain in store.domains.filter(domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN, retired_at__isnull=True).order_by("pk"):
        if domain.verification_status == StoreDomain.VerificationStatus.PENDING and domain.verification_token:
            asked = domain.verification_requested_at
            if asked and now - asked <= PENDING_WINDOW:
                out.append((domain, "verify"))
        elif domain.verification_status == StoreDomain.VerificationStatus.VERIFIED:
            stale = ACTIVE_STALE if domain.is_primary else READINESS_STALE
            last = domain.routing_checked_at
            ready = domain.routing_status == StoreDomain.RoutingStatus.CONNECTED and domain.tls_status == StoreDomain.TlsStatus.READY
            if last is None or now - last >= stale or (not ready and now - last >= timedelta(minutes=10)):
                out.append((domain, "readiness"))
    return out


def recheck_store(store, *, dry_run: bool = False, now=None, verify=None, readiness=None, sleep=None) -> automation.Result:
    verify = verify or (lambda domain: dvs.check_dns_verification(domain=domain, actor=None))
    readiness = readiness or (lambda domain: dvs.refresh_custom_domain_readiness(domain=domain, actor=None))
    now = now or timezone.now()

    def work(dry: bool) -> dict:
        todo = due(store, now)
        metrics = {"due": len(todo), "verified": 0, "readiness_checked": 0, "skipped": 0}
        if dry:
            metrics["hosts"] = [d.hostname for d, _ in todo]
            return metrics
        for domain, action in todo:
            try:
                if action == "verify":
                    metrics["verified"] += 1 if verify(domain) else 0
                else:
                    readiness(domain)
                    metrics["readiness_checked"] += 1
            except dvs.DomainVerificationError:
                metrics["skipped"] += 1                              # the state changed under us (e.g. just verified): nothing to do
        return metrics

    kwargs = {"sleep": sleep} if sleep else {}
    return automation.run(OPERATION, store, work, enabled=enabled(), dry_run=dry_run, require_public=False,
                          should_record=lambda m: bool(m.get("verified")), **kwargs)
