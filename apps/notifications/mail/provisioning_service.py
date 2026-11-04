"""Sender-identity lifecycle: a Store's own custom domain -> ``info@<domain>`` becomes an active email
sender, automatically, with no SMTP credentials and no third-party email account from the merchant.

Two SEPARATE verifications are modelled:
* WEBSITE domain (``StoreDomain.verification_status`` TXT ownership, routing, TLS) — about serving the storefront;
* EMAIL sender (``EmailSenderIdentity``: DKIM verified by the email provider) — about sending mail.
Neither implies the other; the Store panel shows both.

Policy (overrides any shared-domain fallback):
* a Store sends customer email ONLY from its own provider-verified custom domain; there is no RastiSi-domain fallback;
* activation happens ONLY after the provider itself reports the identity verified — never speculatively;
* when email is unavailable, only the email channel is blocked — SMS and the rest of the business keep working
  (``notification_service._deliver_one`` already isolates channel failures; this module only decides whether
  a given Store currently HAS a usable sender, via :func:`active_sender_address`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.models import Store, StoreDomain

from apps.notifications.models import EmailSenderIdentity

from . import dns as dns_provisioning
from .base import PROVIDER_FAILED, PROVIDER_TEMPORARY_FAILURE, PROVIDER_VERIFIED, TransportNotConfigured
from .registry import get_transport

logger = logging.getLogger(__name__)

RECHECK_INTERVAL_HOURS = 6
LOCAL_PART_DEFAULT = "info"

# ``reason_code`` -> (Persian explanation, required corrective action, platform-fixable?, needs domain owner?)
REASON_CATALOG = {
    "no_custom_domain": (
        "فروشگاه هنوز دامنه‌ی اختصاصی ندارد؛ ایمیل فقط از دامنه‌ی خودِ فروشگاه ارسال می‌شود.",
        "یک دامنه‌ی اختصاصی برای فروشگاه ثبت کنید (بخش دامنه)؛ سپس همین صفحه را بررسی کنید.",
        False, True,
    ),
    "dns_pending": (
        "رکوردهای DNS فرستنده هنوز روی دامنه دیده نشده‌اند.",
        "رکوردهای DNS زیر را دقیقاً مطابق مقدارِ نشان‌داده‌شده در DNS دامنه‌ی خود اضافه کنید؛ انتشار DNS تا ۴۸ ساعت طول می‌کشد.",
        False, True,
    ),
    "provider_failed": (
        "ارائه‌دهنده‌ی ایمیل، رکوردهای DNS را نامعتبر یا ناموجود گزارش کرد.",
        "مقادیرِ رکوردهای DNS را با دقت کامل (بدون کم/زیاد) دوباره بررسی و ذخیره کنید؛ سپس «بررسیِ دوباره» را بزنید.",
        False, True,
    ),
    "provider_temporary_failure": (
        "ارائه‌دهنده‌ی ایمیل موقتاً در دسترس نیست.",
        "چیزی از شما لازم نیست؛ راستی‌سی به‌صورت خودکار دوباره تلاش می‌کند.",
        True, False,
    ),
    "provider_not_configured": (
        "اتصال راستی‌سی به ارائه‌دهنده‌ی ایمیل هنوز پیکربندی نشده است.",
        "این مرحله فقط توسطِ تیمِ راستی‌سی قابلِ انجام است.",
        True, False,
    ),
    "platform_disabled": (
        "ارسال ایمیل برای این فروشگاه توسط راستی‌سی موقتاً غیرفعال شده است.",
        "با پشتیبانی راستی‌سی تماس بگیرید.",
        True, False,
    ),
}


@dataclass(frozen=True)
class EmailDiagnostics:
    status: str
    reason_code: str
    reason_text: str
    corrective_action: str
    platform_can_fix: bool
    owner_action_required: bool
    last_checked_at: object = None
    dns_records: tuple = ()
    from_address: str = ""
    dns_auto_requested: bool = False
    responsible_party: str = "—"
    #: WEBSITE-domain state — informational and independent of the email-sender state above
    website_domain: str = ""
    website_status: str = ""
    website_routing: str = ""
    website_tls: str = ""
    #: automatic-DNS result (Persian): why automation is/was not possible and what to do instead
    dns_automation_state: str = ""
    dns_automation_code: str = ""
    dns_automation_reason_fa: str = ""
    dns_automation_action_fa: str = ""
    manual_steps_fa: tuple = ()
    #: SPF/DMARC observations — advisory only, they never change ``status``
    advisory: tuple = ()


def _sender_domain(store: Store) -> StoreDomain | None:
    """The Store's own custom domain used for email. EMAIL-sender verification (DKIM at the email provider) is a
    SEPARATE fact from WEBSITE-domain verification (TXT ownership / routing / TLS): email never waits for, nor
    implies, the website being connected. The provider's DKIM check is the only proof of control for email.
    Selection is sticky (keeps the current sender domain while it is still the Store's non-retired custom domain)
    so a second domain can never silently flip the sender."""
    qs = StoreDomain.objects.filter(
        store=store, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN, retired_at__isnull=True,
    )
    current = EmailSenderIdentity.objects.filter(store=store).values_list("domain_name", flat=True).first()
    if current:
        kept = qs.filter(hostname=current).first()
        if kept is not None:
            return kept
    return qs.order_by("-is_primary", "-verification_status", "id").first()


def _get_or_init(store: Store) -> EmailSenderIdentity:
    identity, _ = EmailSenderIdentity.objects.get_or_create(store=store, defaults={"local_part": LOCAL_PART_DEFAULT})
    return identity


@transaction.atomic
def sync_sender_identity(store: Store, *, actor=None) -> EmailSenderIdentity:
    """Idempotent: safe to call repeatedly (domain connected, periodic recheck, manual retry).

    Never raises for provider/DNS problems — those are recorded on the row as ``ERROR``/``PENDING`` with an
    explicit reason; only truly unexpected bugs propagate."""
    identity = EmailSenderIdentity.objects.select_for_update().filter(store=store).first() or _get_or_init(store)
    before_status = identity.status

    if identity.platform_disabled:
        return _settle(identity, EmailSenderIdentity.Status.INACTIVE, "platform_disabled", "", actor, before_status)

    domain = _sender_domain(store)
    if domain is None:
        identity.domain = None
        identity.domain_name = ""
        return _settle(identity, EmailSenderIdentity.Status.INACTIVE, "no_custom_domain", "", actor, before_status)

    try:
        transport = get_transport()
    except TransportNotConfigured as exc:
        return _settle(identity, EmailSenderIdentity.Status.ERROR, "provider_not_configured", str(exc), actor, before_status)

    if identity.domain_name and identity.domain_name != domain.hostname:
        # the Store's sender domain changed: never carry an old verification over to a different domain
        identity.provider_ref = ""
        identity.verified_at = None
        identity.dns_auto_requested = False
        identity.dns_automation_state = identity.dns_automation_code = identity.dns_automation_detail = ""
    identity.domain = domain
    identity.domain_name = domain.hostname
    if not identity.provider_ref:
        state = transport.create_identity(domain.hostname)
    else:
        state = transport.get_identity(domain.hostname)
        if state.status == "not_found":  # provider lost it (e.g. region change): start over, never assume
            state = transport.create_identity(domain.hostname)

    identity.provider = transport.code
    identity.provider_ref = state.provider_ref or identity.provider_ref
    identity.dns_records = [r.as_dict() for r in state.dns_records]
    if state.dns_records and state.status != PROVIDER_VERIFIED and identity.dns_automation_state != dns_provisioning.REQUESTED:
        # Authorized automatic DNS provisioning — ONLY through a configured integration that controls this zone.
        # "requested" means the zone accepted the records; it is NOT success. Success is claimed only when the email
        # provider itself reports the identity verified (see ACTIVE below). Failures/conflicts are retried on each
        # recheck; "no integration" / "zone not authorized" are recorded as the exact blocking reason.
        outcome = dns_provisioning.try_apply(domain.hostname, state.dns_records)
        identity.dns_automation_state, identity.dns_automation_code = outcome.state, outcome.code
        identity.dns_automation_detail = (outcome.detail or "")[:200]
        identity.dns_auto_requested = outcome.state == dns_provisioning.REQUESTED
    elif state.status == PROVIDER_VERIFIED and identity.dns_automation_state != dns_provisioning.REQUESTED:
        identity.dns_automation_state, identity.dns_automation_code, identity.dns_automation_detail = "", "", ""
    identity.dns_records = dns_provisioning.annotate_published(
        domain.hostname, [r.as_dict() for r in state.dns_records], enabled=transport.code != "fake",
    )
    identity.last_checked_at = timezone.now()
    identity.next_check_at = identity.last_checked_at + timedelta(hours=RECHECK_INTERVAL_HOURS)

    if state.status == PROVIDER_VERIFIED and state.verified_for_sending:
        identity.consecutive_failures = 0
        identity.verified_at = identity.verified_at or timezone.now()
        return _settle(identity, EmailSenderIdentity.Status.ACTIVE, "", "", actor, before_status)
    if state.status == PROVIDER_FAILED:
        identity.consecutive_failures += 1
        return _settle(identity, EmailSenderIdentity.Status.ERROR, "provider_failed", state.detail, actor, before_status)
    if state.status == PROVIDER_TEMPORARY_FAILURE:
        identity.consecutive_failures += 1
        if before_status == EmailSenderIdentity.Status.ACTIVE and identity.consecutive_failures < 3:
            # a provider blip must not take a working sender down (nor spam "problem" notices): keep ACTIVE until
            # the failure persists across consecutive checks; sending itself still fails safe per message.
            return _settle(identity, EmailSenderIdentity.Status.ACTIVE, "", "", actor, before_status)
        return _settle(
            identity, EmailSenderIdentity.Status.ERROR, "provider_temporary_failure", state.detail, actor, before_status,
        )
    return _settle(identity, EmailSenderIdentity.Status.PENDING, "dns_pending", "", actor, before_status)


def _settle(identity, status, reason_code, reason_detail, actor, before_status) -> EmailSenderIdentity:
    identity.status = status
    identity.reason_code = reason_code
    identity.reason_detail = (reason_detail or "")[:300]
    identity.save()
    if before_status != status:
        record_audit_event(
            store=identity.store, actor=actor, action_code="notifications.sender_identity_status_changed",
            object_type="EmailSenderIdentity", object_id=identity.pk, object_label=identity.domain_name,
            before={"status": before_status}, after={"status": status, "reason_code": reason_code},
        )
        _announce_transition(identity, before_status)
    return identity


def _announce_transition(identity: EmailSenderIdentity, before_status: str) -> None:
    """Tell the Store's admins (from RastiSi's own sender — never the Store's broken domain) when email becomes
    active or breaks. Only on a real transition; never raises."""
    from apps.notifications.services.dispatcher import safe_dispatch

    S = EmailSenderIdentity.Status
    stamp = timezone.now().strftime("%Y%m%d%H%M")
    try:
        if identity.status == S.ACTIVE:
            from apps.notifications.services.notification_service import release_held

            release_held(identity.store)
            safe_dispatch(
                "platform.email_sender_active", store=identity.store,
                context={"store_name": identity.store.name, "sender_address": identity.from_address},
                dedupe_key=f"sender-active:{identity.pk}:{stamp}",
            )
        elif identity.status == S.ERROR or (before_status == S.ACTIVE and identity.status != S.ACTIVE):
            text, action, _pf, _owner = REASON_CATALOG.get(identity.reason_code, ("", "", False, False))
            safe_dispatch(
                "platform.email_sender_problem", store=identity.store,
                context={
                    "store_name": identity.store.name, "problem": text or "ارسال ایمیل متوقف شد.",
                    "action": action or "پنل مدیریت ← اعلان‌ها ← هویتِ فرستنده را بررسی کنید.",
                    "panel_url": "پنل مدیریت ← اعلان‌ها ← هویتِ فرستنده",
                },
                dedupe_key=f"sender-problem:{identity.pk}:{identity.reason_code}:{stamp}",
            )
    except Exception:  # noqa: BLE001
        logger.exception("could not queue the sender-status notice (store=%s)", identity.store_id)


def on_domain_verified(domain: StoreDomain, *, actor=None) -> EmailSenderIdentity:
    """Hook: call this right after ``domain_verification_service.check_dns_verification`` succeeds (or whenever
    a Store's primary domain changes) to kick off automatic provisioning. Never raises."""
    try:
        return sync_sender_identity(domain.store, actor=actor)
    except Exception:  # noqa: BLE001 — provisioning must never break the domain-verification request
        logger.exception("sender identity provisioning failed after domain verification (store=%s)", domain.store_id)
        return _get_or_init(domain.store)


def diagnostics(store: Store) -> EmailDiagnostics:
    identity = _get_or_init(store)
    code = identity.reason_code or ("" if identity.status == EmailSenderIdentity.Status.ACTIVE else "no_custom_domain")
    text, action, platform_fix, owner_needed = REASON_CATALOG.get(code, ("", "", False, False))
    site = _sender_domain(store)
    if identity.status == EmailSenderIdentity.Status.ACTIVE:
        responsible = "—"
    elif owner_needed:
        responsible = "مالکِ دامنه"
    elif platform_fix:
        responsible = "راستی‌سی"
    else:
        responsible = "—"
    return EmailDiagnostics(
        status=identity.status, reason_code=code, reason_text=text, corrective_action=action,
        platform_can_fix=platform_fix, owner_action_required=owner_needed,
        dns_records=tuple({**r, "relative": dns_provisioning.relative_name(identity.domain_name, r["name"])}
                          for r in (identity.dns_records or ())),
        from_address=identity.from_address,
        last_checked_at=identity.last_checked_at, dns_auto_requested=identity.dns_auto_requested,
        responsible_party=responsible, website_domain=site.hostname if site else "",
        website_status=site.get_verification_status_display() if site else "",
        website_routing=site.get_routing_status_display() if site else "",
        website_tls=site.get_tls_status_display() if site else "",
        dns_automation_state=identity.dns_automation_state, dns_automation_code=identity.dns_automation_code,
        dns_automation_reason_fa=_auto_text(identity)[0], dns_automation_action_fa=_auto_text(identity)[1],
        manual_steps_fa=dns_provisioning.MANUAL_STEPS_FA if identity.status != EmailSenderIdentity.Status.ACTIVE else (),
        advisory=tuple(dns_provisioning.advisory_checks(identity.domain_name)) if identity.domain_name else (),
    )


def _auto_text(identity) -> tuple[str, str]:
    if identity.status == EmailSenderIdentity.Status.ACTIVE or not identity.dns_records:
        return "", ""
    return dns_provisioning.describe(identity.dns_automation_code or "no_integration")


def active_sender_address(store: Store) -> str:
    """The ONLY function the dispatcher/sender should call to decide whether — and from where — a Store may
    send customer email right now. Empty string = do not send (block the email channel only)."""
    identity = EmailSenderIdentity.objects.filter(store=store).first()
    if identity is None or identity.status != EmailSenderIdentity.Status.ACTIVE or identity.platform_disabled:
        return ""
    return identity.from_address


def due_for_recheck(*, limit: int = 200):
    now = timezone.now()
    return EmailSenderIdentity.objects.filter(
        platform_disabled=False, next_check_at__lte=now,
    ).exclude(status=EmailSenderIdentity.Status.INACTIVE).select_related("store")[:limit]


def revalidate_due() -> dict:
    """Periodic recheck (management command / scheduler). Rechecks domains too (a once-verified domain can be
    unverified later, e.g. the merchant changes DNS or the domain moves to a different store)."""
    checked = changed = 0
    for identity in list(due_for_recheck()):
        before = identity.status
        sync_sender_identity(identity.store)
        checked += 1
        identity.refresh_from_db()
        if identity.status != before:
            changed += 1
    return {"checked": checked, "changed": changed}
