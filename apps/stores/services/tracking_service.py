"""Which analytics/ad identifiers a Store's PUBLIC pages may load.

The Store connected an identifier in the panel (``StoreIntegrationConnection``); this module is the only place that turns it into
something a template may print. Rules:

* only ACTIVE connections of THIS store — never another store's ids;
* every identifier is re-validated against the strict provider pattern at render time (stored data is never trusted into a
  ``<script>``), so a malformed value renders nothing instead of becoming markup;
* nothing is returned at all unless the platform enabled storefront tracking (``RASTISI_STOREFRONT_TRACKING_ENABLED``, default OFF — there is
  no visitor-consent mechanism for tracking cookies in the project, so the safe default is «no third-party tracker before someone decided»);
* nothing is returned for a request the SEO policy says is not a real public page (localhost/QA hosts, unpublished stores,
  admin/builder hosts) — a store that is not live must not feed real analytics or ad accounts.

Only identifiers go into the page. RastiSi never injects seller-supplied HTML/JS."""

from __future__ import annotations

import re

from django.conf import settings

from apps.stores.models import StoreIntegrationConnection

GA4_RE = re.compile(r"^G-[A-Z0-9]{6,10}$")
GTM_RE = re.compile(r"^GTM-[A-Z0-9]{4,8}$")
META_PIXEL_RE = re.compile(r"^\d{10,20}$")

_FIELDS = {
    "google_analytics": ("ga4", "measurement_id", GA4_RE),
    "google_tag_manager": ("gtm", "container_id", GTM_RE),
    "ad_pixel": ("meta_pixel", "pixel_id", META_PIXEL_RE),
}


def tracking_enabled() -> bool:
    return bool(getattr(settings, "RASTISI_STOREFRONT_TRACKING_ENABLED", False))


def active_tracking_ids(store) -> dict[str, str]:
    """``{"ga4": "G-…", "gtm": "GTM-…", "meta_pixel": "123…"}`` — only the active, well-formed ones of ``store``."""
    if store is None or not tracking_enabled():
        return {}
    out: dict[str, str] = {}
    rows = StoreIntegrationConnection.objects.filter(store=store, is_active=True, provider_code__in=list(_FIELDS))
    for conn in rows:
        key, field_key, pattern = _FIELDS[conn.provider_code]
        try:
            value = str((conn.get_credentials() or {}).get(field_key) or "").strip()
        except Exception:                                                  # noqa: BLE001 - unreadable credentials = nothing printed
            continue
        if pattern.match(value):
            out[key] = value
    return out
