"""«دامنه و آدرس فروشگاه» در پنل مدیریت — فقط خواندنی: نشانی‌ها و وضعیتِ واقعیِ ``StoreDomain`` + لینکِ امن به صفحه‌ی مدیریتِ دامنه در پرتالِ مالک.

هیچ Backendِ موازی‌ای اینجا نیست: افزودن/تأیید/فعال‌سازی فقط در ``apps.portal`` (با ``DOMAIN_MANAGE``، Step-Up و Audit) انجام می‌شود."""

from __future__ import annotations

from django.conf import settings
from django.urls import reverse

from apps.stores.hostnames import build_cross_host_url
from apps.stores.models import StoreDomain
from apps.stores.resolution import resolve_storefront_url_for_store
from apps.stores.services import domain_guide_service as guide
from apps.stores.services import domain_verification_service as dvs

_TONE = {"active": "ok", "pending": "warn", "blocked": "danger"}


def portal_domains_url(request, store) -> str:
    """نشانیِ مطلق صفحه‌ی دامنه روی میزبانِ پرتال — با reverse واقعی روی urlconf پلتفرم و حفظِ پورتِ توسعه (نه میزبانِ حدسی)."""
    path = reverse("portal:custom-domains", args=[store.public_id], urlconf="shop_core.urls_platform")
    return build_cross_host_url(request, hostname=settings.RASTISI_PLATFORM_PRIMARY_HOST, path=path)


def domain_overview(store, request, *, can_manage: bool) -> dict:
    connection = dvs.custom_domain_connection_instructions("")
    custom_rows = []
    for domain in store.domains.filter(domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN).order_by("-is_primary", "-created_at"):
        steps = guide.steps(domain, targets_configured=connection["configured"])
        overall = guide.overall_state(steps)
        current = next((s for s in steps if s["state"] in (guide.CURRENT, guide.BLOCKED)), None)
        custom_rows.append({
            "hostname": domain.hostname,
            "is_primary": bool(domain.is_primary and domain.verification_status == StoreDomain.VerificationStatus.VERIFIED),
            "verification": domain.get_verification_status_display(),
            "routing": domain.get_routing_status_display(),
            "tls": domain.get_tls_status_display(),
            "overall": overall,
            "tone": _TONE.get(overall, "warn"),
            "next_step": current["title"] if current else "",
            "next_hint": current["hint"] if current else "",
        })
    platform_domains = [
        {"hostname": d.hostname, "kind": d.get_domain_type_display(), "is_primary": d.is_primary}
        for d in store.domains.exclude(domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN).filter(retired_at__isnull=True).order_by("-is_primary", "hostname")
    ]
    return {
        "storefront_url": resolve_storefront_url_for_store(store, request),
        "platform_domains": platform_domains,
        "custom_domains": custom_rows,
        "targets_configured": connection["configured"],
        "can_manage": can_manage,
        "portal_url": portal_domains_url(request, store) if can_manage else "",
    }
