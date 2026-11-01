"""محدوده‌ی اعلان و کنترلِ دسترسیِ گیرنده (Tenant Isolation + Permission) — تنها جایی که «این کاربر می‌تواند این اعلان را ببیند؟» تصمیم گرفته می‌شود."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.notifications import registry as R
from apps.stores import authorization as auth

PLATFORM_KEY = "platform"


def store_key(store) -> str:
    return f"store:{store.pk}"


def key_for(store=None) -> str:
    return PLATFORM_KEY if store is None else store_key(store)


def is_platform_staff(user) -> bool:
    """همان قاعده‌ی ``portal.platform_admin_views._is_platform_staff`` (staff و superuser و فعال)."""
    return bool(user is not None and getattr(user, "is_authenticated", False) and user.is_active and user.is_staff and user.is_superuser)


def platform_recipients():
    return get_user_model().objects.filter(is_active=True, is_staff=True, is_superuser=True)


def store_recipients(store, permission: str = ""):
    """کاربرانِ دارای عضویتِ ACTIVE در همین فروشگاه (و در صورتِ نیاز دارای مجوز) — هیچ‌وقت عضوِ فروشگاهِ دیگر."""
    from apps.stores.models import StoreMembership

    members = StoreMembership.objects.filter(
        store=store, status=StoreMembership.MembershipStatus.ACTIVE, user__is_active=True,
    ).select_related("user")
    return [m.user for m in members if not permission or auth.membership_has_permission(m, permission)]


def allowed_type_keys(user, store=None) -> list[str]:
    """کلیدِ نوعِ رویدادهایی که ``user`` در این محدوده **اکنون** حق دریافتشان را دارد (برای فیلترِ صندوق؛ لغوِ دسترسی فوراً اثر می‌کند)."""
    if store is None:
        return [k for k, t in R.EVENT_TYPES.items() if t.scope == R.PLATFORM] if is_platform_staff(user) else []
    membership = auth.get_active_membership(user, store)
    if membership is None or not user.is_active:
        return []
    return [k for k, t in R.EVENT_TYPES.items()
            if t.scope == R.STORE and (not t.permission or auth.membership_has_permission(membership, t.permission))]


def can_open_link(user, event) -> bool:
    """مجوزِ صفحه‌ی مقصد: اعلان نمی‌تواند Permissionِ آن صفحه را دور بزند."""
    if event.store_id is None:
        return is_platform_staff(user)
    membership = auth.get_active_membership(user, event.store)
    if membership is None:
        return False
    need = event.link_permission or event.required_permission
    return not need or auth.membership_has_permission(membership, need)
