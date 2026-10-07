"""Authoritative client-IP resolution for security code (rate limits,
Turnstile ``remoteip``, OTP IP budgets).

**The one rule:** forwarded headers are evidence only when the *direct* TCP
peer (``REMOTE_ADDR``) is a proxy the operator explicitly configured in
``settings.RASTISI_TRUSTED_PROXY_CIDRS`` (env ``DJANGO_TRUSTED_PROXY_CIDRS``).
Otherwise ``X-Forwarded-For``, ``Forwarded`` and every CDN-specific header
(``CF-Connecting-IP``, ``True-Client-IP``…) are ignored and the validated peer
address is the client — a direct attacker cannot pick their own bucket by
sending a header.

**Trusted peer:** only ``X-Forwarded-For`` is read, *right to left*. Each hop
that is itself inside a trusted network is a proxy of ours and is skipped; the
first address that is NOT trusted is the client. Everything to the left of it
is attacker-controllable and never examined. At most ``MAX_FORWARDED_HOPS``
entries are inspected; a malformed entry or a chain with no untrusted address
fails safe to the direct peer. ``Forwarded`` and ``CF-Connecting-IP`` are
deliberately never parsed: put Cloudflare-style CDNs behind a reverse proxy
that overwrites ``X-Forwarded-For`` (see PRODUCTION_CONFIGURATION.md §6.2).

This module never touches Store/host resolution.
"""

import ipaddress
from functools import lru_cache

from django.conf import settings

#: Rightmost X-Forwarded-For entries examined; longer chains are cut off from
#: the left (the cut-off part is attacker-controllable anyway).
MAX_FORWARDED_HOPS = 16

#: Rate-limit bucket used when no valid client address can be determined.
UNKNOWN_BUCKET = "unknown"

_UNIX_TOKEN = "unix"
_MAX_IP_TEXT_LENGTH = 45  # longest textual IPv6 form


@lru_cache(maxsize=16)
def _parse_trusted(cidrs):
    networks = []
    unix_trusted = False
    for item in cidrs:
        if str(item).strip().lower() == _UNIX_TOKEN:
            unix_trusted = True
        else:
            networks.append(ipaddress.ip_network(str(item).strip(), strict=False))
    return tuple(networks), unix_trusted


def _trusted():
    return _parse_trusted(tuple(getattr(settings, "RASTISI_TRUSTED_PROXY_CIDRS", ()) or ()))


def _parse_ip(raw):
    """Strictly parse one bare IP (no port/zone/brackets); ``None`` if invalid.
    IPv4-mapped IPv6 (``::ffff:a.b.c.d``) is normalised to IPv4."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or len(text) > _MAX_IP_TEXT_LENGTH or "%" in text:
        return None
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _in_networks(address, networks):
    return any(address in network for network in networks)


def _peer(request):
    """``(address_or_None, peer_is_trusted_proxy)`` for the direct connection."""
    networks, unix_trusted = _trusted()
    raw = request.META.get("REMOTE_ADDR", "")
    address = _parse_ip(raw)
    if address is None:
        # A unix-domain-socket peer has an empty REMOTE_ADDR; it is only a
        # proxy if the operator said so (token ``unix``). Garbage never is.
        return None, bool(unix_trusted and isinstance(raw, str) and raw.strip() == "")
    return address, _in_networks(address, networks)


def is_trusted_proxy_peer(request) -> bool:
    """True when the direct connection comes from a configured trusted proxy."""
    return _peer(request)[1]


def get_client_ip(request) -> str:
    """Return the validated, normalised client IP, or ``""`` if unknown."""
    peer, peer_trusted = _peer(request)
    peer_text = str(peer) if peer is not None else ""
    if not peer_trusted:
        return peer_text

    header = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not isinstance(header, str) or not header.strip():
        return peer_text

    networks, _unix = _trusted()
    parts = header.rsplit(",", MAX_FORWARDED_HOPS)
    if len(parts) > MAX_FORWARDED_HOPS:
        parts = parts[1:]  # drop the unexamined, attacker-controllable left remainder
    for token in reversed(parts):
        hop = _parse_ip(token)
        if hop is None:
            return peer_text  # malformed/empty hop: do not guess
        if not _in_networks(hop, networks):
            return str(hop)
    return peer_text  # every examined hop was a trusted proxy


def get_client_ip_bucket(request) -> str:
    """Rate-limit bucket for the client: the exact IPv4 address, or the /64
    network for IPv6 (a single subscriber commonly owns a whole /64, so a
    per-address bucket would let one host rotate through 2**64 of them)."""
    ip = get_client_ip(request)
    if not ip:
        return UNKNOWN_BUCKET
    address = ipaddress.ip_address(ip)
    if address.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return ip
