"""Store -> RastiChat tenant (Contract v1 §6). One Store maps deterministically to exactly one tenant:
``external_tenant_id = str(store.public_id)`` (the store's stable public UUID). The browser never chooses it."""
from django.conf import settings

from apps.stores.models import Store, StoreDomain

from .. import client

# Seeded ONCE when the tenant is first created (RastiChat never re-applies it, so later manual configuration by the
# store's chat admins is never overwritten): a small icon-only launcher, no questions, conversation on first message.
WIDGET_DEFAULTS = {
    "launcher": {"mode": "icon", "position": "bottom-left"},
    "pre_chat": {"enabled": False},
    "behavior": {"start_mode": "on_first_message"},
    "identity": {"guest_allowed": True},
    "locale": "fa",
    "direction": "rtl",
}


def external_tenant_id(store) -> str:
    return str(store.public_id)


def verified_hostnames(store) -> list[str]:
    """Exact hostnames of this store that RastiSi itself verified and routes (never merchant-claimed, no wildcards)."""
    rows = StoreDomain.objects.filter(
        store=store, verification_status=StoreDomain.VerificationStatus.VERIFIED, retired_at__isnull=True,
    ).values_list("hostname", flat=True)
    hosts = sorted(set(rows))
    hosts += [h.strip() for h in getattr(settings, "RASTICHAT_EXTRA_VERIFIED_DOMAINS", "").split(",") if h.strip()]  # dev/test only
    return hosts


def tenant_payload(store) -> dict:
    return {
        "display_name": store.name,
        "verified_domains": verified_hostnames(store),
        "status": "active" if store.status == Store.Status.ACTIVE else "suspended",
        "defaults": {"widget": WIDGET_DEFAULTS},
        "metadata": {"store_slug": store.slug[:60]} if store.slug.isascii() else {},
    }


def ensure_remote_tenant(store) -> dict:
    """Idempotent: repeating never duplicates; RastiChat updates only integration-managed fields (name, domains, status)."""
    return client.ensure_tenant(external_tenant_id(store), tenant_payload(store))
