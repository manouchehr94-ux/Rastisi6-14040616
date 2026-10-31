"""دامنه‌ی اختصاصیِ اختیاری (Section 12) — چهارمین مفهومِ متمایز §3.6-3.7
(جدا از نامِ نمایشی، نامِ دائمی روی rastisi.ir، و میزبانِ راستیسی).

قاعده‌ی مطلق: یک دامنه هرگز توسطِ خودِ تاجر «تأییدشده» علامت زده نمی‌شود —
تنها راهِ رسیدن به ``VERIFIED``، یک جست‌وجویِ واقعیِ رکوردِ DNS TXT است که
این ماژول خودش انجام می‌دهد (``dnspython``)، نه یک چک‌باکس در فرم. شکستِ
جست‌وجو هرگز چیزی را «تأییدشده» نمی‌کند و فاکتور را در همان وضعیتِ
``PENDING`` نگه می‌دارد تا تاجر بتواند دوباره تلاش کند."""

import ipaddress
import secrets
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone

import dns.exception
import dns.resolver
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.hostnames import is_rastisi_owned_hostname, normalize_hostname
from apps.stores.models import Store, StoreDomain

VERIFICATION_RECORD_PREFIX = "_rastisi-verify"
VERIFICATION_VALUE_PREFIX = "rastisi-verify="
DNS_LOOKUP_TIMEOUT_SECONDS = 5.0
SSL_CHECK_TIMEOUT_SECONDS = 4.0


class DomainVerificationError(Exception):
    """خطای قابل‌نمایشِ درخواست/تأییدِ دامنه‌ی اختصاصی."""


def verification_record_name(hostname: str) -> str:
    return f"{VERIFICATION_RECORD_PREFIX}.{hostname}"


def _normalize_or_raise(raw_hostname: str) -> str:
    try:
        hostname = normalize_hostname(raw_hostname)
    except ValidationError as exc:
        raise DomainVerificationError("؛ ".join(exc.messages)) from exc

    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        pass
    else:
        # An IP literal can never prove ownership with a TXT record, and the later routing/TLS probes must never be pointed at
        # an arbitrary address (SSRF) — only real domain names are accepted.
        raise DomainVerificationError("به‌جای آدرس IP، نامِ دامنه را وارد کنید (مثل shop.example.com).")

    if is_rastisi_owned_hostname(hostname):
        raise DomainVerificationError(
            "دامنه‌ی اختصاصی نمی‌تواند زیردامنه‌ای از خودِ راستیسی باشد؛ برای نامِ دائمی از "
            "بخشِ «نامِ دائمی فروشگاه» استفاده کنید."
        )
    from apps.core import seo_policy  # lazy: keeps this service free of an import-time dependency on the SEO module

    if seo_policy.is_non_public_host(hostname):
        # localhost / *.local / *.test … can never be reached by customers and ownership of them cannot be proven in public DNS
        raise DomainVerificationError("این نام فقط برای آزمایش است و در اینترنت عمومی وجود ندارد؛ یک دامنهٔ واقعی (مثل shop.example.com) وارد کنید.")
    return hostname


@transaction.atomic
def request_custom_domain(*, store: Store, hostname: str, actor) -> StoreDomain:
    """اولین گام: ثبتِ خودِ دامنه، بدونِ هیچ تأییدی هنوز."""
    normalized = _normalize_or_raise(hostname)
    try:
        domain = StoreDomain.objects.create(
            store=store, hostname=normalized, is_primary=False,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.UNVERIFIED,
        )
    except IntegrityError as exc:
        raise DomainVerificationError(f"دامنه‌ی «{normalized}» قبلاً در راستیسی ثبت شده است.") from exc

    record_audit_event(
        store=store, actor=actor, action_code="store.custom_domain_requested",
        object_type="StoreDomain", object_id=domain.pk, object_label=normalized,
    )
    return domain


@transaction.atomic
def begin_dns_verification(*, domain: StoreDomain, actor) -> StoreDomain:
    """توکنِ تأیید تازه می‌سازد و دامنه را به ``PENDING`` می‌برد — تاجر باید
    یک رکوردِ TXT به نامِ ``verification_record_name(domain.hostname)`` با
    مقدارِ ``rastisi-verify={token}`` در DNS خودش اضافه کند."""
    if domain.domain_type != StoreDomain.DomainType.CUSTOM_DOMAIN:
        raise DomainVerificationError("فقط دامنه‌ی اختصاصی نیازِ تأییدِ DNS دارد.")
    if domain.verification_status == StoreDomain.VerificationStatus.VERIFIED:
        raise DomainVerificationError("این دامنه از قبل تأییدشده است.")

    locked = StoreDomain.objects.select_for_update().get(pk=domain.pk)
    locked.verification_token = secrets.token_hex(16)
    locked.verification_status = StoreDomain.VerificationStatus.PENDING
    locked.verification_requested_at = timezone.now()
    locked.save(update_fields=[
        "verification_token", "verification_status", "verification_requested_at", "updated_at",
    ])
    return locked


def _txt_records_match(hostname: str, expected_value: str) -> bool:
    """جست‌وجویِ واقعیِ DNS — هرگز استثنا به بیرون نمی‌اندازد؛ هر خطای
    شبکه/تفکیک‌نام صرفاً «تطبیق نیافت» به‌حساب می‌آید."""
    record_name = verification_record_name(hostname)
    try:
        answers = dns.resolver.resolve(record_name, "TXT", lifetime=DNS_LOOKUP_TIMEOUT_SECONDS)
    except (dns.exception.DNSException, OSError):
        return False

    for rdata in answers:
        # هر رشته‌ی TXT ممکن است به چند بخشِ رشته‌ای تکه‌تکه شده باشد
        # (محدودیتِ ۲۵۵ نویسه‌ایِ هر رشته در پروتکلِ DNS)؛ باید بهم‌بچسبانیم.
        value = b"".join(rdata.strings).decode("utf-8", errors="replace")
        if value.strip() == expected_value:
            return True
    return False


@transaction.atomic
def check_dns_verification(*, domain: StoreDomain, actor) -> bool:
    """تأییدِ واقعیِ DNS را انجام می‌دهد. فقط در صورتِ یافتنِ رکوردِ TXT
    درست، ``VERIFIED`` می‌شود؛ در غیرِ این صورت بدونِ هیچ تغییری False
    برمی‌گرداند (قابلِ تلاشِ دوباره، هرگز قفل‌شده در حالتِ ناموفق)."""
    if domain.verification_status != StoreDomain.VerificationStatus.PENDING or not domain.verification_token:
        raise DomainVerificationError("این دامنه هنوز درخواستِ تأییدی ثبت نکرده است.")

    expected_value = f"{VERIFICATION_VALUE_PREFIX}{domain.verification_token}"
    if not _txt_records_match(domain.hostname, expected_value):
        return False

    locked = StoreDomain.objects.select_for_update().get(pk=domain.pk)
    locked.verification_status = StoreDomain.VerificationStatus.VERIFIED
    locked.verified_at = timezone.now()
    locked.save(update_fields=["verification_status", "verified_at", "updated_at"])

    record_audit_event(
        store=locked.store, actor=actor, action_code="store.custom_domain_verified",
        object_type="StoreDomain", object_id=locked.pk, object_label=locked.hostname,
    )
    return True


@dataclass(frozen=True)
class SslConnectionCheck:
    """نتیجه‌ی «تستِ نهاییِ اتصال» — یک تشخیصِ صرفِ خواندنی، هیچ فیلدی از
    ``StoreDomain`` را تغییر نمی‌دهد (فعال‌سازی همچنان فقط از طریقِ
    ``activate_custom_domain`` انجام می‌شود، نه بر اساسِ نتیجه‌ی این تابع)."""

    reachable: bool
    certificate_expires_at: datetime | None
    error: str


def check_ssl_connection(hostname: str) -> SslConnectionCheck:
    """اتصالِ HTTPS واقعی به ``hostname:443`` را امتحان می‌کند — دقیقاً همان
    الگویِ ``_txt_records_match``: هرگز استثنا به بیرون نمی‌اندازد، هر خطای
    شبکه/گواهی صرفاً «در دسترس نیست» به‌حساب می‌آید، نه یک ۵۰۰."""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=SSL_CHECK_TIMEOUT_SECONDS) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                cert = tls_sock.getpeercert()
    except Exception as exc:  # noqa: BLE001 — هر خطای شبکه/TLS/DNS باید بی‌صدا «ناموفق» شود
        return SslConnectionCheck(reachable=False, certificate_expires_at=None, error=str(exc))

    expires_at = None
    not_after = cert.get("notAfter") if cert else None
    if not_after:
        try:
            expires_at = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime_timezone.utc)
        except ValueError:
            expires_at = None
    return SslConnectionCheck(reachable=True, certificate_expires_at=expires_at, error="")


@dataclass(frozen=True)
class DnsRoutingCheck:
    """Result of checking whether the customer hostname points to RastiSi."""

    configured: bool
    connected: bool
    expected_a_targets: tuple[str, ...]
    observed_a_targets: tuple[str, ...]
    expected_cname: str
    observed_cname: str
    error: str


@dataclass(frozen=True)
class DomainReadinessCheck:
    """Combined persisted DNS-routing + TLS readiness result."""

    routing: DnsRoutingCheck
    tls: SslConnectionCheck | None

    @property
    def ready(self) -> bool:
        return bool(self.routing.connected and self.tls and self.tls.reachable)


def custom_domain_connection_instructions(hostname: str) -> dict:
    """Return deployment-configured A/CNAME values safe to show merchants."""
    a_targets = tuple(
        str(value).strip()
        for value in getattr(settings, "RASTISI_CUSTOM_DOMAIN_A_TARGETS", ())
        if str(value).strip()
    )
    cname_target = str(
        getattr(settings, "RASTISI_CUSTOM_DOMAIN_CNAME_TARGET", "") or ""
    ).strip().lower().rstrip(".")
    return {
        "hostname": hostname,
        "a_targets": a_targets,
        "cname_target": cname_target,
        "configured": bool(a_targets or cname_target),
    }


def _resolve_record_strings(hostname: str, record_type: str) -> tuple[str, ...]:
    answers = dns.resolver.resolve(
        hostname, record_type, lifetime=DNS_LOOKUP_TIMEOUT_SECONDS
    )
    values = []
    for answer in answers:
        if record_type == "CNAME":
            target = getattr(answer, "target", answer)
            value = str(target).strip().lower().rstrip(".")
        else:
            value = str(answer).strip()
        if value:
            values.append(value)
    return tuple(sorted(set(values)))


def check_dns_routing(hostname: str) -> DnsRoutingCheck:
    """Check A/CNAME against the deployment's declared RastiSi targets."""
    instructions = custom_domain_connection_instructions(hostname)
    expected_a = tuple(instructions["a_targets"])
    expected_cname = instructions["cname_target"]
    if not instructions["configured"]:
        return DnsRoutingCheck(
            configured=False,
            connected=False,
            expected_a_targets=expected_a,
            observed_a_targets=(),
            expected_cname=expected_cname,
            observed_cname="",
            error="custom-domain routing targets are not configured",
        )

    observed_a = ()
    observed_cname = ""
    errors = []

    if expected_a:
        try:
            observed_a = _resolve_record_strings(hostname, "A")
        except (dns.exception.DNSException, OSError) as exc:
            errors.append(f"A: {exc}")

    if expected_cname:
        try:
            cname_values = _resolve_record_strings(hostname, "CNAME")
            observed_cname = cname_values[0] if cname_values else ""
        except (dns.exception.DNSException, OSError) as exc:
            errors.append(f"CNAME: {exc}")

    connected = bool(
        set(observed_a).intersection(expected_a)
        or (expected_cname and observed_cname == expected_cname)
    )
    return DnsRoutingCheck(
        configured=True,
        connected=connected,
        expected_a_targets=expected_a,
        observed_a_targets=observed_a,
        expected_cname=expected_cname,
        observed_cname=observed_cname,
        error="; ".join(errors),
    )


def refresh_custom_domain_readiness(*, domain: StoreDomain, actor) -> DomainReadinessCheck:
    """Run real routing/TLS checks and persist their operational state."""
    if domain.domain_type != StoreDomain.DomainType.CUSTOM_DOMAIN:
        raise DomainVerificationError("بررسی اتصال فقط برای دامنه‌ی اختصاصی انجام می‌شود.")
    if domain.verification_status != StoreDomain.VerificationStatus.VERIFIED:
        raise DomainVerificationError("ابتدا مالکیت دامنه را با رکورد TXT تأیید کنید.")

    routing = check_dns_routing(domain.hostname)
    tls_result = check_ssl_connection(domain.hostname) if routing.connected else None
    checked_at = timezone.now()

    with transaction.atomic():
        locked = StoreDomain.objects.select_for_update().get(pk=domain.pk)
        locked.routing_status = (
            StoreDomain.RoutingStatus.CONNECTED
            if routing.connected
            else StoreDomain.RoutingStatus.NOT_CONNECTED
        )
        locked.routing_checked_at = checked_at

        if tls_result is None:
            locked.tls_status = StoreDomain.TlsStatus.UNCHECKED
            locked.tls_checked_at = None
            locked.tls_certificate_expires_at = None
        else:
            locked.tls_status = (
                StoreDomain.TlsStatus.READY
                if tls_result.reachable
                else StoreDomain.TlsStatus.NOT_READY
            )
            locked.tls_checked_at = checked_at
            locked.tls_certificate_expires_at = tls_result.certificate_expires_at

        locked.save(update_fields=[
            "routing_status",
            "routing_checked_at",
            "tls_status",
            "tls_checked_at",
            "tls_certificate_expires_at",
            "updated_at",
        ])

    record_audit_event(
        store=domain.store,
        actor=actor,
        action_code="store.custom_domain_readiness_checked",
        object_type="StoreDomain",
        object_id=domain.pk,
        object_label=domain.hostname,
        after={
            "routing_connected": routing.connected,
            "tls_ready": bool(tls_result and tls_result.reachable),
        },
    )
    return DomainReadinessCheck(routing=routing, tls=tls_result)


def custom_domain_is_ready_for_activation(domain: StoreDomain) -> bool:
    """Require a recent successful routing + TLS check before activation."""
    if (
        domain.routing_status != StoreDomain.RoutingStatus.CONNECTED
        or domain.tls_status != StoreDomain.TlsStatus.READY
        or domain.routing_checked_at is None
        or domain.tls_checked_at is None
    ):
        return False

    max_age = max(
        1,
        int(
            getattr(
                settings,
                "RASTISI_CUSTOM_DOMAIN_READINESS_MAX_AGE_SECONDS",
                900,
            )
        ),
    )
    now = timezone.now()
    return (
        (now - domain.routing_checked_at).total_seconds() <= max_age
        and (now - domain.tls_checked_at).total_seconds() <= max_age
    )


@transaction.atomic
def activate_custom_domain(*, store: Store, domain: StoreDomain, actor) -> StoreDomain:
    """دامنه‌ی اختصاصیِ تأییدشده را دامنه‌ی اصلیِ فروشگاه می‌کند.

    اگر دامنه‌ی اصلیِ قبلی ``PLATFORM_SUBDOMAIN`` باشد (مثلاً
    ``digilool.rastisi.ir``)، آن نام دائمی متعلق به همان Store باقی می‌ماند:
    فقط ``is_primary`` از آن برداشته می‌شود و بازنشسته نمی‌شود تا Middleware
    بتواند صفحات عمومی آن را به دامنه‌ی اختصاصی جدید 301 کند و
    ``/admin-portal/`` همچنان روی میزبان RastiSi قابل استفاده باشد.

    دامنه‌ی آزمایشی تصادفی و دامنه‌ی اختصاصی قدیمی، در صورت جایگزینی،
    همچنان بازنشسته می‌شوند. Step-up OTP
    (action=``custom_domain_activate``) در لایه‌ی ویو اعمال می‌شود، نه اینجا.
    """
    if domain.store_id != store.pk:
        raise DomainVerificationError("این دامنه متعلق به این فروشگاه نیست.")
    if domain.domain_type != StoreDomain.DomainType.CUSTOM_DOMAIN:
        raise DomainVerificationError("فقط دامنه‌ی اختصاصیِ تأییدشده قابلِ فعال‌سازی است.")
    if domain.verification_status != StoreDomain.VerificationStatus.VERIFIED:
        raise DomainVerificationError("این دامنه هنوز تأیید نشده؛ ابتدا تأییدِ DNS را کامل کنید.")

    locked_domain = StoreDomain.objects.select_for_update().get(pk=domain.pk)
    if not custom_domain_is_ready_for_activation(locked_domain):
        raise DomainVerificationError(
            "دامنه هنوز آماده‌ی فعال‌سازی نیست؛ ابتدا «بررسی اتصال و SSL» را با موفقیت کامل کنید."
        )

    locked_store = Store.objects.select_for_update().get(pk=store.pk)
    old_primary = StoreDomain.objects.select_for_update().filter(store=locked_store, is_primary=True).first()
    if old_primary is not None and old_primary.pk != domain.pk:
        old_primary.is_primary = False
        update_fields = ["is_primary", "updated_at"]
        if old_primary.domain_type == StoreDomain.DomainType.PLATFORM_SUBDOMAIN:
            old_primary.retired_at = None
        else:
            old_primary.retired_at = timezone.now()
            update_fields.append("retired_at")
        old_primary.save(update_fields=update_fields)

    locked_domain.is_primary = True
    locked_domain.save(update_fields=["is_primary", "updated_at"])

    record_audit_event(
        store=locked_store, actor=actor, action_code="store.custom_domain_activated",
        object_type="StoreDomain", object_id=locked_domain.pk, object_label=locked_domain.hostname,
        before={"old_primary": old_primary.hostname if old_primary else None},
        after={"hostname": locked_domain.hostname},
    )
    return locked_domain


# ---------------------------------------------------------------------------------------------------------------------------
# One «check my connection» step for the seller panel
# ---------------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DomainAdvanceResult:
    """What ONE «check status» press did. ``outcome`` is one of:

    * ``txt_issued``        — the ownership record was generated (nothing was queried yet)
    * ``txt_missing``       — the TXT record is not visible (yet); the seller has to add / wait for it
    * ``verified_only``     — ownership just got verified but the DNS/HTTPS check could not run (see ``routing``)
    * ``routing_unconfigured`` — the platform operator has not declared the A/CNAME targets: nothing the seller can do
    * ``routing_pending``   — A/CNAME does not reach RastiSi yet
    * ``tls_pending``       — DNS reaches RastiSi, HTTPS is not ready yet
    * ``ready``             — DNS + HTTPS are ready: only the owner-level activation (Step-Up) is left
    * ``active``            — nothing to do, the domain is already the shop's main address
    """

    outcome: str
    ownership_just_verified: bool = False
    routing: DnsRoutingCheck | None = None
    tls: SslConnectionCheck | None = None


def advance_domain_connection(*, domain: StoreDomain, actor) -> DomainAdvanceResult:
    """Do, in order and stopping at the first thing only the seller or the platform can fix, whatever the domain's CURRENT state needs:
    issue the TXT record → verify it → check DNS (A/CNAME) → check HTTPS. It only chains the existing checked functions (the same
    ones the owner portal uses); it never activates a domain (activation stays behind the owner-level Step-Up) and never marks anything
    verified by itself — ``check_dns_verification`` still has to find the real TXT record."""
    if domain.domain_type != StoreDomain.DomainType.CUSTOM_DOMAIN:
        raise DomainVerificationError("فقط دامنه‌ی اختصاصی بررسی اتصال دارد.")
    if domain.is_primary and domain.verification_status == StoreDomain.VerificationStatus.VERIFIED:
        return DomainAdvanceResult(outcome="active")

    just_verified = False
    if domain.verification_status in (StoreDomain.VerificationStatus.UNVERIFIED, StoreDomain.VerificationStatus.FAILED):
        domain = begin_dns_verification(domain=domain, actor=actor)
        return DomainAdvanceResult(outcome="txt_issued")
    if domain.verification_status == StoreDomain.VerificationStatus.PENDING:
        if not check_dns_verification(domain=domain, actor=actor):
            return DomainAdvanceResult(outcome="txt_missing")
        just_verified = True
        domain.refresh_from_db()

    result = refresh_custom_domain_readiness(domain=domain, actor=actor)
    if not result.routing.configured:
        outcome = "routing_unconfigured"
    elif not result.routing.connected:
        outcome = "routing_pending"
    elif not (result.tls and result.tls.reachable):
        outcome = "tls_pending"
    else:
        outcome = "ready"
    return DomainAdvanceResult(outcome=outcome, ownership_just_verified=just_verified, routing=result.routing, tls=result.tls)
