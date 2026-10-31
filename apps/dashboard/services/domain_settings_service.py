"""«دامنه و آدرس فروشگاه» در پنل مدیریت — فقط خواندنی: نشانی‌ها و وضعیتِ واقعیِ ``StoreDomain`` + لینکِ امن به صفحه‌ی مدیریتِ دامنه در پرتالِ مالک.

هیچ Backendِ موازی‌ای اینجا نیست: افزودن/تأیید/فعال‌سازی فقط در ``apps.portal`` (با ``DOMAIN_MANAGE``، Step-Up و Audit) انجام می‌شود."""

from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings
from django.urls import reverse

from apps.stores.hostnames import build_cross_host_url
from apps.stores.models import StoreDomain
from apps.stores.resolution import resolve_storefront_url_for_store
from apps.stores.services import domain_guide_service as guide
from apps.stores.services import domain_verification_service as dvs

_TONE = {"active": "ok", "pending": "warn", "blocked": "danger"}
#: what the seller does next, derived ONLY from the domain's real statuses
ACTION_BEGIN, ACTION_CHECK_TXT, ACTION_CHECK_DNS, ACTION_WAIT_HTTPS, ACTION_ACTIVATE, ACTION_NONE = (
    "begin", "check_txt", "check_dns", "wait_https", "activate", "none")

_SELLER_STATUS = {
    ACTION_BEGIN: ("آمادهٔ شروع بررسی", "warn"),
    ACTION_CHECK_TXT: ("یک اقدام کوتاه از شما لازم است", "warn"),
    ACTION_CHECK_DNS: ("یک اقدام کوتاه از شما لازم است", "warn"),
    ACTION_WAIT_HTTPS: ("در حال اتصال دامنه", "info"),
    ACTION_ACTIVATE: ("آمادهٔ فعال‌سازی نهایی", "ok"),
    ACTION_NONE: ("اتصال موفق", "ok"),
}


def _next_action(domain: StoreDomain) -> str:
    verified = domain.verification_status == StoreDomain.VerificationStatus.VERIFIED
    if not verified:
        return ACTION_BEGIN if domain.verification_status == StoreDomain.VerificationStatus.UNVERIFIED else ACTION_CHECK_TXT
    if domain.routing_status != StoreDomain.RoutingStatus.CONNECTED:
        return ACTION_CHECK_DNS
    if domain.tls_status != StoreDomain.TlsStatus.READY:
        return ACTION_WAIT_HTTPS
    return ACTION_NONE if domain.is_primary else ACTION_ACTIVATE


_STEP_LABEL = {guide.DONE: "انجام شد", guide.CURRENT: "مرحلهٔ فعلی", guide.TODO: "بعداً", guide.BLOCKED: "نیازمند رفع مشکل"}


def portal_domains_url(request, store) -> str:
    """نشانیِ مطلق صفحه‌ی دامنه روی میزبانِ پرتال — با reverse واقعی روی urlconf پلتفرم و حفظِ پورتِ توسعه (نه میزبانِ حدسی)."""
    path = reverse("portal:custom-domains", args=[store.public_id], urlconf="shop_core.urls_platform")
    return build_cross_host_url(request, hostname=settings.RASTISI_PLATFORM_PRIMARY_HOST, path=path)


def _is_local_address(url: str) -> bool:
    """True for a development/QA address (``*.localhost``, ``localhost``, loopback) — never a public address customers can reach."""
    host = (urlsplit(url or "").hostname or "").lower()
    return host == "localhost" or host.endswith(".localhost") or host in {"127.0.0.1", "::1", "0.0.0.0"}


def _status_summary(*, storefront_url: str, is_local: bool, platform_domains: list, custom_rows: list) -> dict:
    """ONE plain-language sentence about where the shop is reachable right now and what (if anything) is left — so a non-technical seller
    does not have to read the tables below to learn it. Pure presentation of data the page already has."""
    primary_custom = next((row for row in custom_rows if row["is_primary"]), None)
    pending_custom = next((row for row in custom_rows if not row["is_primary"]), None)
    public = next((d["hostname"] for d in platform_domains if d["is_primary"]), "") or (platform_domains[0]["hostname"] if platform_domains else "")
    if is_local:
        return {"tone": "warn", "key": "test_environment", "title": "این پنل در محیط آزمایشی/توسعه باز شده است",
                "text": "آدرسی که در مرورگر می‌بینید (مثل localhost) فقط برای آزمایش است و مشتریان واقعی با آن وارد نمی‌شوند. "
                        "آدرس عمومیِ فروشگاه شما در محیط واقعی پایین‌تر نوشته شده است." + (f" آدرس راستی‌سی: {public}" if public else "")}
    if primary_custom:
        return {"tone": "ok", "key": "custom_active", "title": f"فروشگاه شما با دامنهٔ اختصاصیِ {primary_custom['hostname']} آنلاین است",
                "text": "مشتریان با همین دامنه وارد می‌شوند. آدرس رایگانِ راستی‌سی هم همچنان کار می‌کند."}
    if pending_custom:
        step = pending_custom["next_step"] or "بررسی وضعیتِ اتصال"
        return {"tone": "warn", "key": "custom_in_progress", "title": f"اتصالِ دامنهٔ {pending_custom['hostname']} هنوز کامل نشده",
                "text": f"تا آن زمان فروشگاه شما با آدرس راستی‌سی کار می‌کند و چیزی از دسترس خارج نمی‌شود. قدمِ بعدی: {step}."}
    if storefront_url:
        return {"tone": "info", "key": "platform_only", "title": "فروشگاه شما با آدرسِ رایگانِ راستی‌سی آنلاین است",
                "text": "برای حرفه‌ای‌تر شدن می‌توانید یک دامنهٔ اختصاصی (مثل shop.example.com) وصل کنید؛ این کار اختیاری است و می‌توانید هر زمان انجام دهید."}
    return {"tone": "warn", "key": "no_public_address", "title": "هنوز آدرسِ عمومیِ قابل‌استفاده‌ای ثبت نشده",
            "text": "تا ثبتِ آدرس، مشتریان نمی‌توانند فروشگاه را ببینند. با پشتیبانیِ راستی‌سی تماس بگیرید."}


def domain_overview(store, request, *, can_manage: bool) -> dict:
    connection = dvs.custom_domain_connection_instructions("")
    custom_rows = []
    for domain in store.domains.filter(domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN).order_by("-is_primary", "-created_at"):
        steps = guide.steps(domain, targets_configured=connection["configured"])
        action = _next_action(domain)
        overall = guide.overall_state(steps)
        current = next((s for s in steps if s["state"] in (guide.CURRENT, guide.BLOCKED)), None)
        custom_rows.append({
            "id": domain.pk,
            "hostname": domain.hostname,
            "is_primary": bool(domain.is_primary and domain.verification_status == StoreDomain.VerificationStatus.VERIFIED),
            "verification": domain.get_verification_status_display(),
            "routing": domain.get_routing_status_display(),
            "tls": domain.get_tls_status_display(),
            "overall": overall,
            "tone": _TONE.get(overall, "warn"),
            "next_step": current["title"] if current else "",
            "next_hint": current["hint"] if current else "",
            "action": action,
            "seller_status": _SELLER_STATUS[action][0],
            "seller_tone": _SELLER_STATUS[action][1],
            "failed": domain.verification_status == StoreDomain.VerificationStatus.FAILED,
            "txt_record": guide.txt_record(domain) if action in (ACTION_CHECK_TXT,) else None,
            "routing_records": guide.routing_records(domain.hostname) if action in (ACTION_CHECK_DNS, ACTION_WAIT_HTTPS) else None,
            "steps": [{"title": step["title"], "state": step["state"], "state_label": _STEP_LABEL.get(step["state"], "")} for step in steps],
        })
    platform_domains = [
        {"hostname": d.hostname, "kind": d.get_domain_type_display(), "is_primary": d.is_primary}
        for d in store.domains.exclude(domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN).filter(retired_at__isnull=True).order_by("-is_primary", "hostname")
    ]
    storefront_url = resolve_storefront_url_for_store(store, request)
    is_local = _is_local_address(storefront_url)
    return {
        "summary": _status_summary(storefront_url=storefront_url, is_local=is_local, platform_domains=platform_domains, custom_rows=custom_rows),
        "storefront_url": storefront_url,
        "storefront_is_local": is_local,
        "platform_domains": platform_domains,
        "custom_domains": custom_rows,
        "targets_configured": connection["configured"],
        "can_manage": can_manage,
        "portal_url": portal_domains_url(request, store) if can_manage else "",
    }
