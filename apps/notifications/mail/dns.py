"""Automatic provisioning of the SES verification (DKIM) records — ONLY where RastiSi has authorized DNS control.

AUDIT RESULT (see docs/notifications/EMAIL_ENGINE.md §DNS): RastiSi's domain architecture is "bring your own domain".
A merchant's custom domain lives at the merchant's registrar / DNS host; RastiSi only READS it (``dnspython`` TXT/A/CNAME
lookups in ``domain_verification_service``) and tells the merchant which records to add. There is NO DNS-write
integration, credential, API token or delegated zone in the repository, settings, deployment files or docs. Therefore:

* automation is impossible for every merchant-owned domain today, and the panel says exactly that, in Persian, with
  the manual steps (``Outcome.code`` below drives the text);
* the mechanism below activates ONLY for zones the platform owner explicitly lists in ``RASTISI_EMAIL_DNS_ZONES`` AND for
  which a TSIG key is configured (a merchant who delegates their zone to a RastiSi-operated nameserver, or a zone RastiSi
  itself owns). Nothing is guessed from the domain name, nothing is ever invented.

Safety rules enforced in code (and tested):
* only ``CNAME`` records whose name is ``<token>._domainkey.<domain>`` and whose value ends with ``.dkim.amazonses.com``
  can be written — any other record is refused (``record_not_allowed``);
* existing data is never modified or deleted: an identical CNAME is a no-op ("already present"); a different value, or any
  other record at that exact name, is a CONFLICT that is reported, not overwritten;
* "requested" is not "succeeded": a successful update only means the zone accepted it. The sender becomes ACTIVE solely
  when the email provider itself reports the identity verified.

``RASTISI_EMAIL_DNS_PROVISIONER`` may name a different class implementing :class:`DnsProvisioner` (for a DNS host
RastiSi is authorized on, e.g. a vendor API); the contract and the safety checks are shared."""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

SES_DKIM_VALUE_SUFFIX = ".dkim.amazonses.com"
FAKE_DKIM_VALUE_SUFFIX = ".dkim.fake-mail.test"   # the fake provider's records (tests/dev only)

REQUESTED = "requested"        # the authorized DNS integration accepted every record (NOT yet verified by the provider)
NOT_ATTEMPTED = "not_attempted"
FAILED = "failed"

# code -> (state, Persian explanation shown to the merchant, Persian instruction)
OUTCOME_TEXT = {
    "requested": (
        "درخواستِ ثبتِ خودکارِ رکوردها از طریقِ دسترسیِ مجازِ DNS ارسال شد.",
        "نیازی به اقدام نیست؛ پس از انتشارِ DNS، ارائه‌دهنده‌ی ایمیل تأیید می‌کند. تا آن زمان فرستنده فعال نمی‌شود.",
    ),
    "already_present": (
        "رکوردها از قبل در DNS وجود داشتند و تغییری داده نشد.",
        "نیازی به اقدام نیست؛ منتظرِ تأییدِ ارائه‌دهنده‌ی ایمیل بمانید.",
    ),
    "no_integration": (
        "ثبتِ خودکارِ DNS برای این دامنه ممکن نیست: راستی‌سی هیچ دسترسیِ مجازی برای نوشتن در DNS دامنه‌ی شما ندارد "
        "(DNS دامنه نزد ثبت‌کننده‌ی دامنه‌ی شماست و راستی‌سی فقط آن را می‌خواند).",
        "رکوردهای جدولِ زیر را خودتان در پنلِ DNS دامنه اضافه کنید.",
    ),
    "zone_not_authorized": (
        "ثبتِ خودکارِ DNS برای این دامنه ممکن نیست: این دامنه در فهرستِ ناحیه‌های مجازِ راستی‌سی نیست.",
        "رکوردهای جدولِ زیر را خودتان در پنلِ DNS دامنه اضافه کنید (یا با پشتیبانی برای واگذاریِ ناحیه هماهنگ کنید).",
    ),
    "record_conflict": (
        "ثبتِ خودکار انجام نشد: در DNS شما از قبل رکوردی با همین نام ولی مقدارِ متفاوت (یا رکوردی از نوعِ دیگر) وجود دارد. "
        "راستی‌سی رکوردهای موجودِ شما را تغییر یا حذف نمی‌کند.",
        "رکوردِ قدیمیِ هم‌نام را در DNS خود حذف یا اصلاح کنید و سپس «بررسیِ دوباره» را بزنید، یا رکوردهای جدول را دستی اضافه کنید.",
    ),
    "record_not_allowed": (
        "ثبتِ خودکار متوقف شد: رکوردِ درخواستی از نوعِ مجازِ تأییدِ فرستنده (CNAME کلید DKIM) نبود.",
        "این یک خطای داخلی است؛ به پشتیبانی راستی‌سی اطلاع دهید و تا آن زمان رکوردها را دستی اضافه کنید.",
    ),
    "dns_server_error": (
        "ثبتِ خودکار انجام نشد: سرورِ DNS درخواست را نپذیرفت یا در دسترس نبود.",
        "راستی‌سی دوباره تلاش می‌کند. اگر نمی‌خواهید منتظر بمانید، رکوردها را دستی اضافه کنید.",
    ),
    "partial": (
        "ثبتِ خودکارِ DNS فقط برای بخشی از رکوردها انجام شد.",
        "راستی‌سی دوباره تلاش می‌کند؛ رکوردهای باقی‌مانده را می‌توانید دستی اضافه کنید.",
    ),
    "unexpected_error": (
        "ثبتِ خودکار به‌دلیلِ یک خطای غیرمنتظره انجام نشد.",
        "رکوردهای جدول را دستی اضافه کنید و موضوع را به پشتیبانی اطلاع دهید.",
    ),
}
MANUAL_STEPS_FA = (
    "وارد پنلِ DNS دامنه‌ی خود (نزدِ ثبت‌کننده‌ی دامنه یا هر سرویسی که نیم‌سرورهای دامنه را مدیریت می‌کند) شوید.",
    "برای هر ردیفِ جدول یک رکوردِ CNAME بسازید؛ «نام» و «مقدار» را دقیقاً کپی کنید (بدونِ فاصله‌ی اضافه).",
    "اگر سرویسِ شما نامِ دامنه را خودش به انتهای «نام» اضافه می‌کند، فقط «نامِ نسبی» را وارد کنید.",
    "پروکسی/ابرِ نارنجیِ سرویس‌هایی مانندِ Cloudflare را برای این رکوردها خاموش کنید (فقط DNS).",
    "ذخیره کنید؛ انتشارِ DNS تا ۴۸ ساعت زمان می‌برد. سپس «بررسیِ دوباره» را بزنید.",
)


@dataclass(frozen=True)
class Outcome:
    state: str          # REQUESTED | NOT_ATTEMPTED | FAILED
    code: str
    detail: str = ""    # short technical note (no secrets), for operators


class DnsProvisioner(ABC):
    @abstractmethod
    def controls_zone(self, domain: str) -> bool:
        """True ONLY if this deployment holds authorization to write records under ``domain``."""

    @abstractmethod
    def apply(self, domain: str, records) -> Outcome:
        """Create the given records without touching anything else. Must never raise for expected failures."""


def allowed_record(domain: str, record) -> bool:
    """The only records RastiSi may ever write: the provider's DKIM CNAMEs for exactly this domain."""
    name = record.name.lower().rstrip(".")
    value = record.value.lower().rstrip(".")
    return (
        record.type.upper() == "CNAME"
        and name.endswith(f"._domainkey.{domain.lower()}")
        and name.count(".") == domain.count(".") + 2
        and (value.endswith(SES_DKIM_VALUE_SUFFIX) or value.endswith(FAKE_DKIM_VALUE_SUFFIX))
    )


class FakeDnsProvisioner(DnsProvisioner):
    """Test double: controls only the domains in ``zones``; records what it 'wrote'. Enforces the same record allowlist."""

    zones: set = set()
    applied: list = []
    result: Outcome | None = None

    @classmethod
    def reset(cls) -> None:
        cls.zones, cls.applied, cls.result = set(), [], None

    def controls_zone(self, domain: str) -> bool:
        return domain in self.zones

    def apply(self, domain: str, records) -> Outcome:
        if any(not allowed_record(domain, r) for r in records):
            return Outcome(FAILED, "record_not_allowed")
        if self.result is not None:
            return self.result
        self.applied.append((domain, [r.as_dict() for r in records]))
        return Outcome(REQUESTED, "requested")


class Rfc2136DnsProvisioner(DnsProvisioner):
    """RFC 2136 dynamic update (TSIG-signed) against a nameserver that is authoritative for a zone the platform owner
    listed in ``RASTISI_EMAIL_DNS_ZONES``. Configuration (all from the environment; nothing has a default secret):

    * ``RASTISI_EMAIL_DNS_RFC2136_SERVER`` / ``_PORT``   — the primary nameserver accepting updates
    * ``RASTISI_EMAIL_DNS_RFC2136_KEY_NAME`` / ``_KEY_SECRET`` / ``_KEY_ALGORITHM`` — TSIG key (secret is base64)
    * ``RASTISI_EMAIL_DNS_ZONES``                         — comma-separated zone apexes this key may write
    """

    TTL = 300
    TIMEOUT = 5

    def __init__(self):
        self.server = getattr(settings, "RASTISI_EMAIL_DNS_RFC2136_SERVER", "")
        self.port = int(getattr(settings, "RASTISI_EMAIL_DNS_RFC2136_PORT", 53) or 53)
        self.key_name = getattr(settings, "RASTISI_EMAIL_DNS_RFC2136_KEY_NAME", "")
        self.key_secret = getattr(settings, "RASTISI_EMAIL_DNS_RFC2136_KEY_SECRET", "")
        self.algorithm = getattr(settings, "RASTISI_EMAIL_DNS_RFC2136_KEY_ALGORITHM", "hmac-sha256")
        self.zones = tuple(z.lower().strip(".") for z in getattr(settings, "RASTISI_EMAIL_DNS_ZONES", ()) if z)

    @property
    def configured(self) -> bool:
        return bool(self.server and self.key_name and self.key_secret and self.zones)

    def zone_for(self, domain: str) -> str:
        domain = domain.lower().strip(".")
        matches = [z for z in self.zones if domain == z or domain.endswith("." + z)]
        return max(matches, key=len) if matches else ""

    def controls_zone(self, domain: str) -> bool:
        return self.configured and bool(self.zone_for(domain))

    # -- network primitives (isolated so tests can stub them; no network in the test-suite) ------------------------
    def _query(self, name: str, rdtype: str):
        import dns.message
        import dns.query

        return dns.query.tcp(dns.message.make_query(name, rdtype), self.server, port=self.port, timeout=self.TIMEOUT)

    def _send_update(self, update):
        import dns.query

        return dns.query.tcp(update, self.server, port=self.port, timeout=self.TIMEOUT)

    def _existing(self, name: str) -> tuple[list[str], bool]:
        """(CNAME targets at ``name``, whether any OTHER record type exists at ``name``)."""
        import dns.rcode

        targets, other = [], False
        for rdtype in ("CNAME", "TXT", "A", "AAAA", "MX"):
            response = self._query(name, rdtype)
            if response.rcode() not in (dns.rcode.NOERROR, dns.rcode.NXDOMAIN):
                raise RuntimeError(f"query rcode {dns.rcode.to_text(response.rcode())}")
            for rrset in response.answer:
                if rrset.rdtype == 5:  # CNAME
                    targets += [str(r.target).lower().rstrip(".") for r in rrset]
                elif rdtype != "CNAME":
                    other = True
        return targets, other

    def apply(self, domain: str, records) -> Outcome:
        import dns.rcode
        import dns.tsigkeyring
        import dns.update

        if not self.controls_zone(domain):
            return Outcome(NOT_ATTEMPTED, "zone_not_authorized")
        if any(not allowed_record(domain, r) for r in records):
            return Outcome(FAILED, "record_not_allowed")
        zone = self.zone_for(domain)
        try:
            keyring = dns.tsigkeyring.from_text({self.key_name: self.key_secret})
            base64.b64decode(self.key_secret, validate=True)
            to_add = []
            for r in records:
                targets, other = self._existing(r.name)
                want = r.value.lower().rstrip(".")
                if targets and targets != [want]:
                    return Outcome(FAILED, "record_conflict", "different CNAME already present")
                if not targets and other:
                    return Outcome(FAILED, "record_conflict", "other record type present at the name")
                if not targets:
                    to_add.append(r)
            if not to_add:
                return Outcome(REQUESTED, "already_present")
            added = 0
            for r in to_add:
                update = dns.update.Update(zone, keyring=keyring, keyalgorithm=self.algorithm)
                relative = r.name.lower().rstrip(".")[: -(len(zone) + 1)]
                update.add(relative, self.TTL, "CNAME", r.value.rstrip(".") + ".")
                response = self._send_update(update)
                if response.rcode() != dns.rcode.NOERROR:
                    logger.warning("DNS update refused: %s", dns.rcode.to_text(response.rcode()))
                    return Outcome(FAILED, "partial" if added else "dns_server_error", dns.rcode.to_text(response.rcode()))
                added += 1
            return Outcome(REQUESTED, "requested")
        except Exception as exc:  # noqa: BLE001 — timeouts, bad key material, refused connections …
            logger.warning("DNS provisioning error: %s", type(exc).__name__)
            return Outcome(FAILED, "dns_server_error", type(exc).__name__)


def get_provisioner() -> DnsProvisioner | None:
    path = getattr(settings, "RASTISI_EMAIL_DNS_PROVISIONER", "")
    if path:
        return import_string(path)()
    rfc = Rfc2136DnsProvisioner()
    return rfc if rfc.configured else None


def try_apply(domain: str, records) -> Outcome:
    """Never raises. The returned ``Outcome.code`` drives the Persian text in the store panel."""
    try:
        provisioner = get_provisioner()
        if provisioner is None:
            return Outcome(NOT_ATTEMPTED, "no_integration")
        if not provisioner.controls_zone(domain):
            return Outcome(NOT_ATTEMPTED, "zone_not_authorized")
        return provisioner.apply(domain, list(records))
    except Exception:  # noqa: BLE001
        logger.exception("automatic DNS provisioning crashed; falling back to manual records")
        return Outcome(FAILED, "unexpected_error")


def describe(code: str) -> tuple[str, str]:
    """(Persian explanation, Persian instruction) for an outcome code."""
    return OUTCOME_TEXT.get(code, OUTCOME_TEXT["unexpected_error"])


def annotate_published(domain: str, records: list, *, enabled: bool) -> list:
    """Adds ``published`` (True/False/None=unknown) to each record dict by a real DNS lookup. Observation only — it never
    changes a status; ACTIVE still requires the email provider's own confirmation."""
    if not enabled:
        return [{**r, "published": None} for r in records]
    return [{**r, "published": _lookup(r)} for r in records]


def relative_name(domain: str, name: str) -> str:
    name = name.rstrip(".")
    return name[: -(len(domain) + 1)] if name.endswith("." + domain) else name


def _lookup(record: dict):
    try:
        import dns.exception
        import dns.resolver

        answers = dns.resolver.resolve(record["name"], record["type"], lifetime=3)
        wanted = record["value"].strip().lower().rstrip(".")
        for rdata in answers:
            got = str(getattr(rdata, "target", rdata)).strip().lower().rstrip(".").strip('"')
            if got == wanted:
                return True
        return False
    except dns.resolver.NXDOMAIN:
        return False
    except Exception:  # noqa: BLE001 — timeouts / no network: unknown, never "published"
        return None


# --- SPF / DMARC advisory (READ-ONLY, NEVER GATING) ---------------------------------------------------------------------
# DKIM (the three CNAMEs above) is what the provider verifies and what makes a sender ACTIVE. SPF and DMARC records on the
# merchant's own domain improve inbox placement and let the domain owner see/spoof-protect their mail, but a missing record
# NEVER blocks or changes a sender's status. With SES' default MAIL FROM, DMARC passes through DKIM alignment, so SPF on the
# merchant domain is optional; a DMARC policy is recommended.
SPF_RECOMMENDED = "v=spf1 include:amazonses.com ~all"
DMARC_RECOMMENDED = "v=DMARC1; p=none;"


def _txt_values(name: str):
    """List of TXT strings at ``name`` ([] = the name has no TXT), or ``None`` when the lookup could not be completed."""
    try:
        import dns.resolver

        answers = dns.resolver.resolve(name, "TXT", lifetime=3)
        return ["".join(part.decode() if isinstance(part, bytes) else part for part in rdata.strings) for rdata in answers]
    except Exception as exc:  # noqa: BLE001
        import dns.resolver

        if isinstance(exc, (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer)):
            return []
        return None


def advisory_checks(domain: str, *, enabled: bool | None = None, txt_lookup=None) -> list[dict]:
    """SPF + DMARC observations for ``domain``. ``status`` is one of ok | missing | unknown | not_checked. Advisory only."""
    if enabled is None:
        enabled = bool(getattr(settings, "RASTISI_EMAIL_DNS_ADVISORY_LOOKUP", False))
    lookup = txt_lookup or _txt_values
    out = []
    for kind, name, prefix, recommended, label in (
        ("spf", domain, "v=spf1", SPF_RECOMMENDED, "SPF"),
        ("dmarc", f"_dmarc.{domain}", "v=dmarc1", DMARC_RECOMMENDED, "DMARC"),
    ):
        if not enabled:
            status = "not_checked"
        else:
            values = lookup(name)
            status = "unknown" if values is None else ("ok" if any(v.strip().lower().startswith(prefix) for v in values) else "missing")
        text = {
            "ok": f"رکورد {label} روی دامنه‌ی شما دیده شد.",
            "missing": f"رکورد {label} روی دامنه‌ی شما دیده نشد. این فقط یک توصیه است و ارسال ایمیل را متوقف نمی‌کند.",
            "unknown": f"بررسی رکورد {label} انجام نشد (خطای شبکه یا DNS).",
            "not_checked": f"رکورد {label} به‌صورت خودکار بررسی نمی‌شود؛ مقدار پیشنهادی را در DNS دامنه اضافه کنید.",
        }[status]
        out.append({"kind": kind, "label": label, "name": name, "type": "TXT", "status": status,
                    "recommended": recommended, "text_fa": text})
    return out
