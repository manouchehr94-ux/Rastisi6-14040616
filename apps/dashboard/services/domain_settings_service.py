"""«دامنه و آدرس فروشگاه» در پنل مدیریت — نمایشِ وضعیتِ واقعیِ ``StoreDomain`` به زبانِ ساده (یک «فاز» و یک اقدامِ بعدی برای هر دامنه).

هیچ Backendِ موازی‌ای اینجا نیست: افزودن/تأیید/بررسی همه از ``domain_verification_service`` می‌آیند (همان سرویسِ پرتال، با ``DOMAIN_MANAGE``
و Audit)؛ فقط «فعال‌سازیِ نهایی» که Step-Up می‌خواهد در پرتالِ مالک می‌ماند."""

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


# ---- the seller-facing phase of a domain: ONE state, ONE next action --------------------------------------------------------------
PHASE_READY_TO_REGISTER = "ready_to_register"        # no domain yet (page level)
PHASE_AWAITING_OWNERSHIP = "awaiting_ownership"      # TXT record: issue it / add it / waiting for it to be visible
PHASE_NEEDS_ACTION = "needs_action"                  # ownership OK, the A/CNAME record has to be added
PHASE_CHECKING = "checking"                          # DNS reaches RastiSi, HTTPS is being prepared (nothing for the seller to do)
PHASE_AWAITING_FINAL = "awaiting_final"              # everything ready; only the owner-level confirmation (Step-Up) is left
PHASE_ACTIVE = "active"
PHASE_ERROR = "error"                                # something failed and must be corrected
PHASE_PLATFORM_WAIT = "platform_wait"                # RastiSi's own connection targets are not configured: nothing the seller can do

PHASE_LABELS = {
    PHASE_READY_TO_REGISTER: ("آماده ثبت", "info"),
    PHASE_AWAITING_OWNERSHIP: ("در انتظار تأیید مالکیت", "warn"),
    PHASE_NEEDS_ACTION: ("نیازمند اقدام شما", "warn"),
    PHASE_CHECKING: ("در حال بررسی اتصال", "info"),
    PHASE_AWAITING_FINAL: ("در انتظار تأیید نهایی", "ok"),
    PHASE_ACTIVE: ("متصل و فعال", "ok"),
    PHASE_ERROR: ("خطا / نیازمند اصلاح", "danger"),
    PHASE_PLATFORM_WAIT: ("در انتظار تنظیمات راستی‌سی", "info"),
}
NOTHING_TO_DO = "فعلاً نیازی به انجام کاری از طرف شما نیست."
#: the seller-panel button a phase offers («begin» = issue the ownership record, «refresh» = check where things stand, «activate» = final confirmation)
BUTTON_NONE, BUTTON_BEGIN, BUTTON_REFRESH, BUTTON_ACTIVATE = "", "begin", "refresh", "activate"


def domain_phase(domain: StoreDomain, *, targets_configured: bool) -> str:
    """Pure function of the domain's REAL statuses (never a stored flag)."""
    V = StoreDomain.VerificationStatus
    if domain.verification_status == V.VERIFIED:
        if domain.is_primary:
            return PHASE_ACTIVE
        if domain.routing_status != StoreDomain.RoutingStatus.CONNECTED:
            return PHASE_NEEDS_ACTION if targets_configured else PHASE_PLATFORM_WAIT
        if domain.tls_status != StoreDomain.TlsStatus.READY:
            return PHASE_CHECKING
        return PHASE_AWAITING_FINAL
    return PHASE_ERROR if domain.verification_status == V.FAILED else PHASE_AWAITING_OWNERSHIP


def _phase_guidance(domain: StoreDomain, phase: str, *, fresh: bool) -> dict:
    """The one sentence + one button for a phase. Plain language: no DNS vocabulary beyond the record the seller must paste."""
    unverified = domain.verification_status == StoreDomain.VerificationStatus.UNVERIFIED
    if phase == PHASE_AWAITING_OWNERSHIP:
        if unverified:
            return {"next_text": "برای شروع، «شروع تأیید مالکیت» را بزنید تا رکوردِ لازم ساخته شود.", "button": BUTTON_BEGIN, "button_label": "شروع تأیید مالکیت", "needs_nothing": False}
        return {"next_text": "رکوردِ پایین را در پنلِ DNSِ دامنه‌تان اضافه کنید و بعد «بررسی وضعیت» را بزنید.", "button": BUTTON_REFRESH, "button_label": "بررسی وضعیت", "needs_nothing": False}
    if phase == PHASE_NEEDS_ACTION:
        return {"next_text": "مالکیتِ دامنه تأیید شد. حالا رکوردِ اتصال را در پنلِ DNS اضافه کنید و بعد «بررسی وضعیت» را بزنید.", "button": BUTTON_REFRESH, "button_label": "بررسی وضعیت", "needs_nothing": False}
    if phase == PHASE_CHECKING:
        return {"next_text": "اتصال DNS برقرار است و راستی‌سی در حال آماده‌سازیِ HTTPS است؛ این صفحه وضعیت را خودش به‌روز می‌کند.", "button": BUTTON_REFRESH, "button_label": "بررسی دوباره", "needs_nothing": True}
    if phase == PHASE_AWAITING_FINAL:
        if fresh:
            return {"next_text": "همه‌چیز آماده است؛ فقط یک تأییدِ نهایی با کدِ پیامکی لازم است تا دامنه، آدرسِ اصلیِ فروشگاه شود.", "button": BUTTON_ACTIVATE, "button_label": "تأیید نهایی و فعال‌سازی", "needs_nothing": False}
        return {"next_text": "همه‌چیز آماده است؛ نتیجهٔ آخرین بررسی قدیمی شده، یک‌بار دیگر بررسی کنید تا تأییدِ نهایی باز شود.", "button": BUTTON_REFRESH, "button_label": "بررسی دوباره", "needs_nothing": False}
    if phase == PHASE_ACTIVE:
        return {"next_text": "دامنه فعال است و مشتریان با آن وارد فروشگاه می‌شوند.", "button": BUTTON_NONE, "button_label": "", "needs_nothing": True}
    if phase == PHASE_PLATFORM_WAIT:
        return {"next_text": "مقصدِ اتصالِ دامنه‌های اختصاصی هنوز توسط راستی‌سی تنظیم نشده؛ تا آن زمان این مرحله ممکن نیست.", "button": BUTTON_NONE, "button_label": "", "needs_nothing": True}
    return {"next_text": "تأییدِ مالکیت انجام نشد. «تلاش دوباره» رکوردِ تازه می‌سازد؛ آن را دقیق کپی و اضافه کنید.", "button": BUTTON_REFRESH, "button_label": "تلاش دوباره", "needs_nothing": False}


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
        phase = domain_phase(domain, targets_configured=connection["configured"])
        phase_label, phase_tone = PHASE_LABELS[phase]
        guidance = _phase_guidance(domain, phase, fresh=guide.readiness_is_fresh(domain))
        custom_rows.append({
            "phase": phase, "phase_label": phase_label, "phase_tone": phase_tone, **guidance,
            "nothing_text": NOTHING_TO_DO if guidance["needs_nothing"] else "",
            #: the page may re-check by itself (a few times, at long intervals) only while RastiSi or the DNS is the one being waited for
            "auto_refresh": phase in (PHASE_AWAITING_OWNERSHIP, PHASE_NEEDS_ACTION, PHASE_CHECKING) and not domain.verification_status == StoreDomain.VerificationStatus.UNVERIFIED,
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
            "txt_record": guide.txt_record(domain) if phase in (PHASE_AWAITING_OWNERSHIP, PHASE_ERROR) else None,
            "routing_records": guide.routing_records(domain.hostname) if phase in (PHASE_NEEDS_ACTION, PHASE_CHECKING, PHASE_PLATFORM_WAIT) else None,
            "all_txt_record": guide.txt_record(domain),
            "all_routing_records": guide.routing_records(domain.hostname),
            "steps": [{"title": step["title"], "state": step["state"], "state_label": _STEP_LABEL.get(step["state"], "")} for step in steps],
        })
    platform_domains = [
        {"hostname": d.hostname, "kind": d.get_domain_type_display(), "is_primary": d.is_primary}
        for d in store.domains.exclude(domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN).filter(retired_at__isnull=True).order_by("-is_primary", "hostname")
    ]
    storefront_url = resolve_storefront_url_for_store(store, request)
    is_local = _is_local_address(storefront_url)
    ready_label, ready_tone = PHASE_LABELS[PHASE_READY_TO_REGISTER]
    return {
        "register_phase": {"phase": PHASE_READY_TO_REGISTER, "label": ready_label, "tone": ready_tone,
                           "text": "دامنهٔ خودتان (مثل shop.example.com) را وارد کنید؛ بقیهٔ مراحل را راستی‌سی راهنمایی می‌کند." if not custom_rows else ""},
        "any_auto_refresh": any(row["auto_refresh"] for row in custom_rows),
        "summary": _status_summary(storefront_url=storefront_url, is_local=is_local, platform_domains=platform_domains, custom_rows=custom_rows),
        "storefront_url": storefront_url,
        "storefront_is_local": is_local,
        "platform_domains": platform_domains,
        "custom_domains": custom_rows,
        "targets_configured": connection["configured"],
        "can_manage": can_manage,
        "portal_url": portal_domains_url(request, store) if can_manage else "",
    }
