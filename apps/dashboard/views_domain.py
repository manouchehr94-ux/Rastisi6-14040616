"""Custom-domain actions INSIDE the seller panel (this store's own admin host) — the seller no longer has to leave the panel to start
connecting a domain.

No new domain logic lives here: every action calls the ONE domain service (``domain_verification_service``) that the owner portal
calls, behind the same canonical permission (``DOMAIN_MANAGE``), tenant scoping (the Store comes from the request host, the domain from
THAT Store), audit logging and anti-takeover rules (a hostname can belong to one Store only). Activation as the shop's main address
stays behind the Step-Up confirmation of the owner portal — the single place the seller is handed over, and it is said so on the page."""

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from apps.core.services.rate_limit import RateLimitExceeded, RateLimitUnavailable, enforce_rate_limit
from apps.stores.models import StoreDomain
from apps.stores.resolution import resolve_store_for_service
from apps.stores.authorization import DOMAIN_MANAGE
from apps.stores.services import domain_verification_service as dvs
from apps.stores.services.domain_typo_service import suggest_domain_typo
from apps.stores.hostnames import normalize_hostname
from django.core.exceptions import ValidationError

from .decorators import permission_required, staff_required

DOMAIN_PAGE = "/admin-portal/settings/?section=domain"


#: DNS / HTTPS look-ups are made on every «check status»: bounded per Store+domain so a seller (or a stuck page) cannot hammer resolvers
_CHECK_RATE_LIMIT = {"max_attempts": 8, "window_seconds": 60}


def _check_allowed(request, store, domain) -> bool:
    """False (with a message) when this domain was checked too often in the last minute."""
    try:
        enforce_rate_limit("domain.check", f"{store.public_id}:{domain.pk}", **_CHECK_RATE_LIMIT)
    except RateLimitExceeded:
        messages.warning(request, "بررسی‌ها پشت‌سرهم انجام شد؛ یک دقیقه صبر کنید و دوباره بزنید.")
        return False
    except RateLimitUnavailable as exc:
        messages.error(request, str(exc))
        return False
    return True


def _custom_domain_or_404(store, domain_id) -> StoreDomain:
    domain = StoreDomain.objects.filter(
        pk=domain_id, store=store, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN, retired_at__isnull=True,
    ).first()
    if domain is None:
        raise Http404("domain not found")
    return domain


@require_POST
@staff_required
@permission_required(DOMAIN_MANAGE)
def settings_domain_add(request):
    store = resolve_store_for_service(request)
    hostname = (request.POST.get("hostname") or "").strip()
    try:
        dvs.request_custom_domain(store=store, hostname=hostname, actor=request.user)
    except dvs.DomainVerificationError as exc:
        messages.error(request, str(exc))
        return redirect(DOMAIN_PAGE)
    domain = StoreDomain.objects.filter(store=store, hostname=normalize_hostname(hostname), retired_at__isnull=True).first()
    try:
        if domain is not None:
            dvs.begin_dns_verification(domain=domain, actor=request.user)     # only generates the record: no network call, nothing activated
    except dvs.DomainVerificationError:
        domain = None
    if domain is not None:
        messages.success(request, "دامنه ثبت شد و رکوردِ تأییدِ مالکیت آماده است؛ آن را در پنلِ DNSِ دامنه‌تان اضافه کنید و «بررسی وضعیت» را بزنید.")
    else:
        messages.success(request, "دامنه ثبت شد؛ مرحلهٔ بعد تأییدِ مالکیت است — «شروع تأیید مالکیت» را بزنید.")
    try:
        suggestion = suggest_domain_typo(store=store, hostname=normalize_hostname(hostname))
    except ValidationError:
        suggestion = None
    if suggestion:
        messages.warning(request, f"⚠️ این دامنه شبیهِ «{suggestion}» به نظر می‌رسد — اگر اشتباهِ تایپی بوده، دامنهٔ درست را جداگانه اضافه کنید.")
    return redirect(DOMAIN_PAGE)


@require_POST
@staff_required
@permission_required(DOMAIN_MANAGE)
def settings_domain_begin(request, domain_id):
    store = resolve_store_for_service(request)
    domain = _custom_domain_or_404(store, domain_id)
    try:
        dvs.begin_dns_verification(domain=domain, actor=request.user)
    except dvs.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "رکورد TXT آماده شد؛ آن را در پنلِ DNSِ دامنه‌تان اضافه کنید و بعد «بررسی مجدد» را بزنید.")
    return redirect(DOMAIN_PAGE)


@require_POST
@staff_required
@permission_required(DOMAIN_MANAGE)
def settings_domain_check(request, domain_id):
    store = resolve_store_for_service(request)
    domain = _custom_domain_or_404(store, domain_id)
    if not _check_allowed(request, store, domain):
        return redirect(DOMAIN_PAGE)
    try:
        verified = dvs.check_dns_verification(domain=domain, actor=request.user)
    except dvs.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        if verified:
            messages.success(request, "مالکیتِ دامنه تأیید شد؛ حالا رکوردهای اتصال (A یا CNAME) را ثبت کنید.")
        else:
            messages.warning(request, "رکورد TXT هنوز پیدا نشد یا مقدارش فرق دارد؛ انتشارِ DNS ممکن است کمی طول بکشد — چند دقیقه بعد دوباره بررسی کنید.")
    return redirect(DOMAIN_PAGE)


@require_POST
@staff_required
@permission_required(DOMAIN_MANAGE)
def settings_domain_readiness(request, domain_id):
    store = resolve_store_for_service(request)
    domain = _custom_domain_or_404(store, domain_id)
    if not _check_allowed(request, store, domain):
        return redirect(DOMAIN_PAGE)
    try:
        result = dvs.refresh_custom_domain_readiness(domain=domain, actor=request.user)
    except dvs.DomainVerificationError as exc:
        messages.error(request, str(exc))
        return redirect(DOMAIN_PAGE)
    if not result.routing.configured:
        messages.warning(request, "مقصدِ اتصالِ دامنه‌های اختصاصی هنوز توسطِ راستی‌سی تنظیم نشده؛ تا آن زمان فعال‌سازی ممکن نیست.")
    elif not result.routing.connected:
        messages.warning(request, f"رکوردهای A/CNAME دامنهٔ «{domain.hostname}» هنوز به راستی‌سی نرسیده‌اند؛ پس از ثبت، کمی صبر کنید و دوباره بررسی کنید.")
    elif result.tls and result.tls.reachable:
        messages.success(request, f"DNS و HTTPS دامنهٔ «{domain.hostname}» آماده است؛ فقط فعال‌سازیِ نهایی (با تأییدِ دوباره) مانده است.")
    else:
        messages.warning(request, f"DNS دامنهٔ «{domain.hostname}» متصل است و راستی‌سی در حال آماده‌سازیِ HTTPS است؛ چند دقیقه بعد دوباره بررسی کنید.")
    return redirect(DOMAIN_PAGE)


#: what the seller is told after ONE «check status» press (level, text)
_ADVANCE_MESSAGES = {
    "txt_issued": (messages.SUCCESS, "رکوردِ تأییدِ مالکیت ساخته شد؛ آن را در پنلِ DNSِ دامنه‌تان اضافه کنید و دوباره «بررسی وضعیت» را بزنید."),
    "txt_missing": (messages.WARNING, "رکوردِ تأییدِ مالکیت هنوز پیدا نشد یا مقدارش فرق دارد. انتشارِ DNS ممکن است کمی طول بکشد؛ چند دقیقه بعد دوباره بررسی کنید."),
    "routing_unconfigured": (messages.INFO, "مقصدِ اتصالِ دامنه‌های اختصاصی هنوز توسطِ راستی‌سی تنظیم نشده؛ تا آن زمان ادامهٔ مسیر ممکن نیست و کاری از شما برنمی‌آید."),
    "routing_pending": (messages.WARNING, "رکوردِ اتصال هنوز به راستی‌سی نرسیده است؛ پس از ثبتِ رکورد کمی صبر کنید و دوباره بررسی کنید."),
    "tls_pending": (messages.INFO, "DNS متصل است و راستی‌سی در حال آماده‌سازیِ HTTPS است؛ چند دقیقه بعد دوباره بررسی کنید. فعلاً نیازی به انجام کاری از طرف شما نیست."),
    "ready": (messages.SUCCESS, "DNS و HTTPS آماده است؛ فقط تأییدِ نهایی (با کدِ پیامکی) مانده است."),
    "active": (messages.INFO, "این دامنه همین حالا آدرسِ اصلیِ فروشگاه است."),
}


@require_POST
@staff_required
@permission_required(DOMAIN_MANAGE)
def settings_domain_refresh(request, domain_id):
    """THE one «check status» button: issues the ownership record, verifies it, checks DNS and HTTPS — whatever the domain's current state
    needs next (``domain_verification_service.advance_domain_connection``). Activation is never done here (owner-level Step-Up)."""
    store = resolve_store_for_service(request)
    domain = _custom_domain_or_404(store, domain_id)
    wants_json = request.headers.get("x-requested-with") == "fetch"
    if not _check_allowed(request, store, domain):
        return JsonResponse({"ok": False, "reason": "rate_limited"}, status=429) if wants_json else redirect(DOMAIN_PAGE)
    try:
        result = dvs.advance_domain_connection(domain=domain, actor=request.user)
    except dvs.DomainVerificationError as exc:
        messages.error(request, str(exc))
        return JsonResponse({"ok": False, "reason": "error"}, status=400) if wants_json else redirect(DOMAIN_PAGE)
    level, text = _ADVANCE_MESSAGES[result.outcome]
    if result.ownership_just_verified:
        text = "مالکیتِ دامنه تأیید شد. " + text
    # the page's own background re-check stays silent unless something actually moved forward (no message spam every few seconds)
    if not wants_json or result.ownership_just_verified or result.outcome == "ready":
        messages.add_message(request, level, text)
    return JsonResponse({"ok": True, "outcome": result.outcome}) if wants_json else redirect(DOMAIN_PAGE)
