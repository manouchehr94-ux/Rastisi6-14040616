"""مدیریت اعضای تیم فروشگاه (Staff/Membership) — افزودن، تغییر نقش، لغو عضویت، انتقال مالکیت.

بر پایه‌ی مدل و پایاییِ ``StoreMembership`` (Phase 1B) و کلید مجوز
``STAFF_MANAGE`` در ``apps.stores.authorization`` بنا شده است — این ماژول
هیچ قید یا نقشِ تازه‌ای اضافه نمی‌کند، فقط لایه‌ی سرویسِ عملیاتی روی
مدلِ از پیش موجود است.

جریان دعوتِ توکنی/تأییدشده با پیامک (invited -> پذیرشِ خودِ کاربر) عمداً
پیاده‌سازی نشده: صاحبِ فروشگاه دارد یک عضوِ تیمِ خودش (شناخته‌شده، نه یک
غریبه‌ی ناشناس) را اضافه می‌کند، پس افزودن بلافاصله عضویتِ ACTIVE می‌سازد
(مشابه رفتار «افزودنِ عضو تیم» در اغلب پنل‌های ادمین ساده). این محدودیت در
گزارش تکمیل پنل مدیریت مستند شده است.
"""

import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.models import StoreMembership

User = get_user_model()

_PHONE_RE = re.compile(r"^09\d{9}$")

#: نقش‌هایی که از طریق این سرویس قابل‌واگذاری‌اند — OWNER عمداً حذف شده چون
#: این فروشگاه دقیقاً یک مالکِ فعال دارد (قید ``uniq_active_owner_per_store``)
#: و واگذاریِ آن باید از مسیرِ صریحِ ``transfer_ownership`` عبور کند، نه از
#: مسیرِ عمومیِ افزودن/تغییرِ نقش.
ASSIGNABLE_ROLES = tuple(
    (value, label) for value, label in StoreMembership.Role.choices
    if value != StoreMembership.Role.OWNER
)
_ASSIGNABLE_ROLE_VALUES = frozenset(value for value, _ in ASSIGNABLE_ROLES)


class MembershipError(Exception):
    """خطای قابل‌نمایش هنگام مدیریت اعضای تیم فروشگاه."""


def _normalize_phone(phone: str) -> str:
    phone = (phone or "").strip()
    if not _PHONE_RE.match(phone):
        raise MembershipError("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.")
    return phone


def _validate_assignable_role(role: str) -> None:
    if role not in _ASSIGNABLE_ROLE_VALUES:
        raise MembershipError("نقش انتخاب‌شده نامعتبر است.")


_STATUS_SORT_ORDER = {
    StoreMembership.MembershipStatus.ACTIVE: 0,
    StoreMembership.MembershipStatus.INVITED: 1,
    StoreMembership.MembershipStatus.REVOKED: 2,
}


def list_memberships(store) -> list[StoreMembership]:
    """اعضای این فروشگاه را برمی‌گرداند: فعال‌ها ابتدا، سپس دعوت‌شده‌ها، سپس لغوشده‌ها؛ درون هر گروه، جدیدترین‌ها بالاتر."""
    memberships = list(
        StoreMembership.objects.filter(store=store).select_related("user", "invited_by")
    )
    return sorted(
        memberships,
        key=lambda m: (_STATUS_SORT_ORDER.get(m.status, 9), -m.created_at.timestamp()),
    )


def active_owner_count(store) -> int:
    return StoreMembership.objects.filter(
        store=store, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
    ).count()


@transaction.atomic
def add_staff_member(store, *, phone: str, role: str, invited_by) -> StoreMembership:
    """کاربری را (با ساختنِ حسابِ کاربری در صورت نبود) عضوِ فعالِ این فروشگاه می‌کند.

    اگر پیش‌تر عضویتی (با هر وضعیتی) برای همین (فروشگاه، کاربر) وجود داشته
    باشد — طبق قید ``uniq_membership_per_store_user`` نمی‌توان ردیف دوم
    ساخت — همان ردیف را با نقشِ تازه به ACTIVE برمی‌گرداند، به‌جای خطای
    یکپارچگیِ پایگاه‌داده.
    """
    phone = _normalize_phone(phone)
    _validate_assignable_role(role)

    # گیتِ صندلی (checkpoint 5A، ADR-69/§27): فقط وقتی این عملیات یک صندلیِ
    # تازه مصرف می‌کند (کاربرِ تازه، یا احیایِ عضویتِ لغوشده) گیت اعمال
    # می‌شود — تغییرِ نقشِ عضوِ از‌پیش‌شمرده‌شده صندلی اضافه نمی‌کند. پیش از
    # ساختِ حسابِ کاربری بررسی می‌شود تا حسابِ یتیم ساخته نشود.
    _existing_user = User.objects.filter(username=phone).first()
    _adds_seat = True
    if _existing_user is not None:
        _m = StoreMembership.objects.filter(store=store, user=_existing_user).first()
        if _m is not None and _m.status in (
            StoreMembership.MembershipStatus.ACTIVE, StoreMembership.MembershipStatus.INVITED,
        ):
            _adds_seat = False
    if _adds_seat:
        from apps.subscriptions.services.enforcement import enforce_can_add_staff

        enforce_can_add_staff(store)

    user = User.objects.filter(username=phone).select_for_update().first()
    if user is None:
        user = User.objects.create_user(username=phone, is_staff=True)
        user.set_unusable_password()
        user.save(update_fields=["password"])
    elif not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])

    existing = StoreMembership.objects.select_for_update().filter(store=store, user=user).first()
    if existing is not None:
        if existing.status == StoreMembership.MembershipStatus.ACTIVE:
            raise MembershipError("این کاربر از قبل عضو فعال این فروشگاه است.")
        existing.role = role
        existing.status = StoreMembership.MembershipStatus.ACTIVE
        existing.invited_by = invited_by
        existing.accepted_at = timezone.now()
        existing.revoked_at = None
        try:
            existing.full_clean()
        except ValidationError as exc:
            raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
        existing.save()
        return existing

    membership = StoreMembership(
        store=store, user=user, role=role,
        status=StoreMembership.MembershipStatus.ACTIVE,
        invited_by=invited_by, accepted_at=timezone.now(),
    )
    try:
        membership.full_clean()
    except ValidationError as exc:
        raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    membership.save()
    record_audit_event(
        store=store, actor=invited_by, action_code="staff.added",
        object_type="StoreMembership", object_id=membership.pk, object_label=phone,
        after={"role": role},
    )
    return membership


@transaction.atomic
def _notify_chat_if_access_lost(membership: StoreMembership) -> None:
    """RastiChat adapter: a revoked member, or one whose new role has no chat role, loses chat access promptly
    (best effort, after commit, no-op unless chat is enabled for the store)."""
    from apps.chat_integration.services import hooks, identity_service

    if (membership.status != StoreMembership.MembershipStatus.ACTIVE
            or identity_service.staff_role_for(membership, surface="customers") is None):
        hooks.membership_removed(membership)


def change_role(membership: StoreMembership, *, new_role: str, actor=None) -> StoreMembership:
    if membership.role == StoreMembership.Role.OWNER:
        raise MembershipError("نقشِ مالک را نمی‌توان مستقیماً تغییر داد؛ از «انتقال مالکیت» استفاده کنید.")
    _validate_assignable_role(new_role)
    old_role = membership.role
    membership.role = new_role
    try:
        membership.full_clean()
    except ValidationError as exc:
        raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    membership.save(update_fields=["role", "updated_at"])
    record_audit_event(
        store=membership.store, actor=actor, action_code="staff.role_changed",
        object_type="StoreMembership", object_id=membership.pk, object_label=membership.user.username,
        before={"role": old_role}, after={"role": new_role},
    )
    _notify_chat_if_access_lost(membership)
    return membership


@transaction.atomic
def revoke_membership(membership: StoreMembership, *, actor=None) -> StoreMembership:
    if membership.role == StoreMembership.Role.OWNER:
        raise MembershipError("نمی‌توان مالکِ فروشگاه را حذف کرد؛ ابتدا مالکیت را به عضوِ دیگری منتقل کنید.")
    if membership.status == StoreMembership.MembershipStatus.REVOKED:
        raise MembershipError("این عضویت پیش‌تر لغو شده است.")
    membership.status = StoreMembership.MembershipStatus.REVOKED
    membership.revoked_at = timezone.now()
    try:
        membership.full_clean()
    except ValidationError as exc:
        raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    membership.save(update_fields=["status", "revoked_at", "updated_at"])
    record_audit_event(
        store=membership.store, actor=actor, action_code="staff.revoked",
        object_type="StoreMembership", object_id=membership.pk, object_label=membership.user.username,
    )
    _notify_chat_if_access_lost(membership)
    return membership


@transaction.atomic
def reactivate_membership(membership: StoreMembership, *, actor=None) -> StoreMembership:
    if membership.status == StoreMembership.MembershipStatus.ACTIVE:
        raise MembershipError("این عضویت هم‌اکنون فعال است.")
    # احیایِ عضویتِ لغوشده یک صندلیِ تازه مصرف می‌کند (ADR-69/§27).
    if membership.status != StoreMembership.MembershipStatus.INVITED:
        from apps.subscriptions.services.enforcement import enforce_can_add_staff

        enforce_can_add_staff(membership.store)
    membership.status = StoreMembership.MembershipStatus.ACTIVE
    membership.accepted_at = timezone.now()
    membership.revoked_at = None
    try:
        membership.full_clean()
    except ValidationError as exc:
        raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    membership.save(update_fields=["status", "accepted_at", "revoked_at", "updated_at"])
    record_audit_event(
        store=membership.store, actor=actor, action_code="staff.reactivated",
        object_type="StoreMembership", object_id=membership.pk, object_label=membership.user.username,
    )
    return membership


@transaction.atomic
def transfer_ownership(store, *, current_owner: StoreMembership, new_owner: StoreMembership, actor=None) -> None:
    """مالکیتِ فروشگاه را از ``current_owner`` به ``new_owner`` منتقل می‌کند.

    هر دو ردیف قفل و به‌ترتیب به‌روزرسانی می‌شوند (ابتدا خلعِ مالکِ فعلی،
    سپس ارتقای مالکِ جدید) تا قیدِ ``uniq_active_owner_per_store`` (دقیقاً
    یک مالکِ فعال) در هیچ لحظه‌ای نقض نشود.
    """
    current = StoreMembership.objects.select_for_update().get(pk=current_owner.pk)
    new = StoreMembership.objects.select_for_update().get(pk=new_owner.pk)

    if current.store_id != store.id or new.store_id != store.id:
        raise MembershipError("این عضویت متعلق به این فروشگاه نیست.")
    if current.role != StoreMembership.Role.OWNER or current.status != StoreMembership.MembershipStatus.ACTIVE:
        raise MembershipError("عضویتِ فعلی، مالکِ فعالِ این فروشگاه نیست.")
    if new.status != StoreMembership.MembershipStatus.ACTIVE:
        raise MembershipError("عضوِ مقصد باید عضویتِ فعال داشته باشد.")
    if new.pk == current.pk:
        raise MembershipError("مالک هم‌اکنون همین عضو است.")

    current.role = StoreMembership.Role.ADMINISTRATOR
    current.save(update_fields=["role", "updated_at"])
    new.role = StoreMembership.Role.OWNER
    new.save(update_fields=["role", "updated_at"])
    record_audit_event(
        store=store, actor=actor, action_code="staff.ownership_transferred",
        object_type="StoreMembership", object_id=new.pk, object_label=new.user.username,
        before={"previous_owner": current.user.username}, after={"new_owner": new.user.username},
    )
