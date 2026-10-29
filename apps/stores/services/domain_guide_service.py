"""Presentation helpers for the custom-domain guide (portal page + admin overview). Pure functions over ``StoreDomain`` rows and the
real deployment targets — nothing here talks to DNS, TLS or the database; the checks stay in ``domain_verification_service``.

* The A/CNAME values shown come ONLY from ``domain_verification_service.custom_domain_connection_instructions`` (settings
  ``RASTISI_CUSTOM_DOMAIN_A_TARGETS`` / ``RASTISI_CUSTOM_DOMAIN_CNAME_TARGET``). Not configured ⇒ the guide says so; no value is invented.
* Host/Name hints (``@`` vs a sub-label) use a conservative heuristic for common Iranian/International two-level suffixes and always
  carry a note to double-check in the registrar panel."""

from __future__ import annotations

from apps.stores.models import StoreDomain
from apps.stores.services import domain_verification_service as dvs

TWO_LEVEL_SUFFIXES = frozenset({
    "co.ir", "ac.ir", "org.ir", "gov.ir", "net.ir", "sch.ir", "id.ir", "or.ir",
    "co.uk", "org.uk", "ac.uk", "com.au", "net.au", "org.au", "co.nz", "co.za", "com.br", "com.tr", "co.in", "co.jp",
})

DONE, CURRENT, TODO, BLOCKED = "done", "current", "todo", "blocked"


def _labels(hostname: str) -> list[str]:
    return [p for p in str(hostname or "").lower().strip(".").split(".") if p]


def sub_labels(hostname: str) -> list[str]:
    """Labels left of the registrable domain (``shop.example.com`` → ``["shop"]``; ``example.com`` / ``example.co.ir`` → ``[]``)."""
    labels = _labels(hostname)
    keep = 3 if len(labels) >= 3 and ".".join(labels[-2:]) in TWO_LEVEL_SUFFIXES else 2
    return labels[:-keep] if len(labels) > keep else []


def is_root_domain(hostname: str) -> bool:
    return not sub_labels(hostname)


def record_host(hostname: str) -> str:
    """Host/Name field of an A/CNAME record in most registrar panels."""
    parts = sub_labels(hostname)
    return ".".join(parts) if parts else "@"


def txt_host_relative(hostname: str) -> str:
    parts = sub_labels(hostname)
    return dvs.VERIFICATION_RECORD_PREFIX + ("." + ".".join(parts) if parts else "")


def txt_record(domain: StoreDomain) -> dict | None:
    if not domain.verification_token:
        return None
    return {
        "type": "TXT",
        "host": txt_host_relative(domain.hostname),
        "host_full": dvs.verification_record_name(domain.hostname),
        "value": f"{dvs.VERIFICATION_VALUE_PREFIX}{domain.verification_token}",
    }


def routing_records(hostname: str) -> dict:
    """A/CNAME rows to show. ``configured=False`` ⇒ the platform operator has not set targets yet (nothing is guessed)."""
    info = dvs.custom_domain_connection_instructions(hostname)
    root = is_root_domain(hostname)
    rows = []
    for target in info["a_targets"]:
        rows.append({"type": "A", "host": record_host(hostname), "value": target, "recommended": root, "kind": "a"})
    if info["cname_target"]:
        rows.append({"type": "CNAME", "host": record_host(hostname), "value": info["cname_target"], "recommended": not root, "kind": "cname",
                     "note": "برای دامنه‌ی ریشه معمولاً CNAME مجاز نیست؛ از A استفاده کنید." if root else ""})
    return {"configured": info["configured"], "rows": rows, "is_root": root, "host": record_host(hostname)}


def readiness_is_fresh(domain: StoreDomain) -> bool:
    return dvs.custom_domain_is_ready_for_activation(domain)


def steps(domain: StoreDomain, *, targets_configured: bool) -> list[dict]:
    """The six guide steps with a state each (done / current / todo / blocked) and, where useful, a short actionable hint."""
    verified = domain.verification_status == StoreDomain.VerificationStatus.VERIFIED
    routed = domain.routing_status == StoreDomain.RoutingStatus.CONNECTED
    tls_ok = domain.tls_status == StoreDomain.TlsStatus.READY
    fresh = verified and routed and tls_ok and readiness_is_fresh(domain)
    active = bool(domain.is_primary and verified)

    def state(done: bool, ready: bool) -> str:
        return DONE if done else (CURRENT if ready else TODO)

    s3 = state(verified, True)
    s4 = state(routed, verified and targets_configured)
    if verified and not targets_configured and not routed:
        s4 = BLOCKED
    s5 = state(tls_ok, verified and routed)
    s6 = DONE if active else (CURRENT if fresh else TODO)
    hints: dict[int, str] = {}
    if domain.verification_status == StoreDomain.VerificationStatus.FAILED:
        hints[3] = "رکورد TXT پیدا نشد یا مقدار آن فرق دارد. نوع (TXT)، نام (Host) و مقدار را دقیق کپی کنید و چند دقیقه صبر کنید؛ گاهی تا چند ساعت طول می‌کشد."
    elif domain.verification_status == StoreDomain.VerificationStatus.PENDING:
        hints[3] = "پس از افزودن رکورد TXT در پنل دامنه، دکمه‌ی «بررسی مجدد» را بزنید. انتشار DNS ممکن است کمی طول بکشد."
    if verified and not targets_configured:
        hints[4] = "مقصد اتصال دامنه‌های اختصاصی هنوز توسط مدیر زیرساخت راستی‌سی تنظیم نشده است؛ تا آن زمان این مرحله ممکن نیست."
    elif verified and not routed:
        hints[4] = ("رکورد A یا CNAME را دقیقاً مطابق جدول ثبت کنید. اگر از Cloudflare یا CDN مشابه استفاده می‌کنید، حالت «پروکسی» را "
                    "موقتاً خاموش کنید. رکوردهای قدیمی همان Host را حذف کنید.")
    if verified and routed and not tls_ok:
        hints[5] = "DNS درست است اما گواهی HTTPS هنوز آماده نیست. چند دقیقه بعد دوباره بررسی کنید؛ گواهی بعد از اتصال DNS صادر می‌شود."
    if verified and routed and tls_ok and not fresh and not active:
        hints[6] = "نتیجه‌ی آخرین بررسی قدیمی شده است. برای فعال‌سازی، یک‌بار دیگر «بررسی اتصال DNS و SSL» را بزنید."
    titles = [
        (1, "تهیه و مالکیت دامنه", DONE),
        (2, "ثبت دامنه در راستی‌سی", DONE),
        (3, "تأیید مالکیت با رکورد TXT", s3),
        (4, "اتصال دامنه (A یا CNAME)", s4),
        (5, "بررسی DNS و HTTPS", s5),
        (6, "فعال‌سازی به‌عنوان دامنه‌ی اصلی", s6),
    ]
    return [{"n": n, "title": t, "state": st, "hint": hints.get(n, "")} for n, t, st in titles]


def overall_state(steps_list: list[dict]) -> str:
    if all(s["state"] == DONE for s in steps_list):
        return "active"
    current = next((s for s in steps_list if s["state"] in (CURRENT, BLOCKED)), None)
    if current is None:
        return "pending"
    return "blocked" if current["state"] == BLOCKED else "pending"
