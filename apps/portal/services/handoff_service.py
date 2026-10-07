"""پل ورود از پرتال مالک به میزبان مجزای پنل مدیریت هر فروشگاه (ADR-98).

``SESSION_COOKIE_DOMAIN`` در این پروژه عمداً تنظیم نشده (کوکی‌های host-only)؛ پس
نشست واردشده‌ی مالک روی میزبان پرتال (مثلاً app.rastisi.ir) روی میزبان متفاوت
``{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`` وجود ندارد. این ماژول یک بلیت
کوتاه‌عمر و یک‌بارمصرف می‌سازد که ویوی سمت میزبان مدیریت
(``apps.dashboard.views.consume_admin_handoff``) مصرف می‌کند و بلافاصله ``login()``
واقعی جنگو را برای همان میزبان صدا می‌زند."""

from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.stores.authorization import get_active_membership
from apps.stores.models import Store

from ..models import AdminHandoffTicket

TICKET_TTL_SECONDS = 600

#: Section 4 — مدت اعتبار توکنِ امضاشده‌ی «بازگشت به Merchant Admin پس از ورود
#: مرکزی». پنجره‌ی کوتاه: فقط باید یک دور ورود (مثلاً OTP) را تحمل کند، نه یک
#: جلسه‌ی مرورگر.
ADMIN_RETURN_TOKEN_MAX_AGE_SECONDS = 600
_ADMIN_RETURN_SALT = "portal.admin_return_token"


class HandoffError(Exception):
    """صدور یا مصرف بلیت ورود به پنل مدیریت ممکن نیست."""


def build_admin_return_token(*, admin_subdomain: str, destination_path: str) -> str:
    """توکنِ امضاشده (HMAC، ``django.core.signing``) می‌سازد که پس از ورود مرکزی، مسیر
    بازگشت به دقیقاً همین (admin_subdomain, destination_path) را بدون امکان دست‌کاری حمل
    می‌کند (Section 4).

    یک URL خام نیست — یک payload امضاشده است؛ پس هرگز نمی‌تواند به مقصد دلخواه بیرونی
    اشاره کند (open redirect): مصرف‌کننده (``apps.portal.views``) همیشه خودش
    ``https://{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}/...`` را می‌سازد، نه اینکه URL
    را مستقیماً از توکن بخواند. توکن هیچ هویتی حمل نمی‌کند و اعتباری نمی‌دهد؛ دسترسی همیشه
    با عضویت فعال کاربرِ واردشده در ``issue_ticket`` تعیین می‌شود."""
    signer = signing.TimestampSigner(salt=_ADMIN_RETURN_SALT)
    return signer.sign_object({"admin_subdomain": admin_subdomain, "destination_path": destination_path})


def decode_admin_return_token(token: str):
    """توکن را رمزگشایی می‌کند اگر معتبر و تازه باشد، وگرنه ``None`` — هرگز Exception
    پرتاب نمی‌کند (ورودیِ کاربر است و همیشه می‌تواند نامعتبر باشد). مسیرِ مقصد باید زیرِ
    ``/admin-portal/`` باشد."""
    signer = signing.TimestampSigner(salt=_ADMIN_RETURN_SALT)
    try:
        payload = signer.unsign_object(token, max_age=ADMIN_RETURN_TOKEN_MAX_AGE_SECONDS)
    except (signing.BadSignature, signing.SignatureExpired):
        return None
    admin_subdomain = payload.get("admin_subdomain")
    destination_path = payload.get("destination_path")
    if not admin_subdomain or not destination_path or not destination_path.startswith("/admin-portal/"):
        return None
    return admin_subdomain, destination_path


def issue_support_ticket(*, actor, store: Store, destination_path: str = "/admin-portal/") -> AdminHandoffTicket:
    """بلیتِ «ورودِ پشتیبانی» — برخلاف ``issue_ticket``، ``actor`` (مدیر پلتفرم) نیازی
    به عضویت در این Store ندارد؛ به‌جایش بلیت برای همان مالکِ فعالِ Store صادر می‌شود تا
    مصرف‌کننده (``consume_ticket`` → ``apps.dashboard.views.consume_admin_handoff``) بدون
    هیچ تغییری در منطقِ ورود/دسترسی کار کند — فقط ``issued_by_platform_admin`` این بلیت را از
    یک handoff معمولیِ مالک متمایز می‌کند، و صفحه‌ی مصرف‌کننده از روی همین فیلد نشانه‌ی «حالت
    پشتیبانی» را در سشن می‌گذارد."""
    from apps.stores.models import StoreMembership

    owner_membership = (
        store.memberships.filter(
            role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        ).select_related("user").first()
    )
    if owner_membership is None:
        raise HandoffError("این فروشگاه مالکِ فعالی ندارد؛ ورودِ پشتیبانی ممکن نیست.")

    return AdminHandoffTicket.objects.create(
        user=owner_membership.user, store=store, destination_path=destination_path,
        expires_at=timezone.now() + timedelta(seconds=TICKET_TTL_SECONDS),
        issued_by_platform_admin=actor,
    )


def issue_ticket(*, user, store: Store, destination_path: str = "/admin-portal/") -> AdminHandoffTicket:
    """فقط برای (user, store)ای که عضویتِ **فعال** دارد بلیت صادر می‌کند — هرگز برای
    فروشگاهی که کاربر عضوش نیست یا عضویتش دعوت‌شده/لغوشده است. این تنها نقطه‌ای است که
    ورود مرکزی را به دسترسی به یک Store تبدیل می‌کند."""
    membership = get_active_membership(user, store)
    if membership is None:
        raise HandoffError("شما عضوِ فعالِ این فروشگاه نیستید")

    return AdminHandoffTicket.objects.create(
        user=user, store=store, destination_path=destination_path,
        expires_at=timezone.now() + timedelta(seconds=TICKET_TTL_SECONDS),
    )


@transaction.atomic
def consume_ticket(token: str, *, store: Store):
    """بلیت را اتمیک می‌خواند و بلافاصله مصرف‌شده علامت می‌زند (``select_for_update`` تا دو
    مصرف‌کننده‌ی هم‌زمان هر کدام یک نسخه‌ی قدیمی نخوانند) و کاربر متعلق به آن را برمی‌گرداند.
    ``store`` باید دقیقاً همان Storeای باشد که بلیت برایش صادر شده — بلیت فروشگاهی دیگر، حتی
    معتبر و مصرف‌نشده، اینجا رد می‌شود. بلیت نامعتبر/منقضی/مصرف‌شده/فروشگاه نادرست ``None``
    برمی‌گرداند."""
    # ``issued_by_platform_admin`` is deliberately left out of
    # ``select_related`` here: it is a nullable ForeignKey, so joining it
    # turns this into a LEFT OUTER JOIN — and PostgreSQL rejects
    # ``SELECT ... FOR UPDATE`` across the nullable side of an outer join
    # with ``NotSupportedError`` (SQLite has no such restriction, which is
    # why this only ever surfaced in production). Accessing
    # ``ticket.issued_by_platform_admin`` below still works — Django just
    # issues one small extra SELECT for it instead of joining.
    ticket = (
        AdminHandoffTicket.objects.select_for_update()
        .select_related("user", "store")
        .filter(token=token, store=store)
        .first()
    )
    if ticket is None or not ticket.is_usable:
        return None

    ticket.consumed_at = timezone.now()
    ticket.save(update_fields=["consumed_at", "updated_at"])
    return ticket.user, ticket.destination_path, ticket.issued_by_platform_admin

