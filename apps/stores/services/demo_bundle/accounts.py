"""The two (and only two) install-time accounts.

* ``platform_owner`` - platform superuser + staff (platform admin host only).
* ``shops_admin``    - plain user holding the ACTIVE OWNER membership of every
  demo store (never staff, never superuser).

Passwords are supplied by the caller at install time and are never defaulted,
logged, printed or stored anywhere but the Django password hash.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.stores.models import Store, StoreMembership

PLATFORM_OWNER = "platform_owner"
SHOPS_ADMIN = "shops_admin"


class AccountError(Exception):
    pass


def _set_password_if_needed(user, password, created, reset_password):
    if password is None:
        if created:
            raise AccountError(f"a password is required to create {user.username}")
        return False
    if not created and not reset_password:
        return False
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise AccountError(f"password for {user.username} rejected: {'; '.join(exc.messages)}") from exc
    user.set_password(password)
    return True


@transaction.atomic
def ensure_accounts(
    *,
    platform_owner_password: str | None,
    shops_admin_password: str | None,
    store_slugs: list[str],
    reset_password: bool = False,
    platform_owner_email: str = "",
    shops_admin_email: str = "",
) -> dict:
    User = get_user_model()
    stores = list(Store.objects.filter(slug__in=store_slugs))
    missing = sorted(set(store_slugs) - {s.slug for s in stores})
    if missing:
        raise AccountError(f"store(s) not found (import them first): {', '.join(missing)}")

    summary: dict = {"created": [], "memberships": [], "password_set": []}

    owner, created = User.objects.get_or_create(username=PLATFORM_OWNER, defaults={"email": platform_owner_email})
    if _set_password_if_needed(owner, platform_owner_password, created, reset_password):
        summary["password_set"].append(PLATFORM_OWNER)
    owner.is_superuser = owner.is_staff = owner.is_active = True
    owner.save()
    if created:
        summary["created"].append(PLATFORM_OWNER)

    admin, created = User.objects.get_or_create(username=SHOPS_ADMIN, defaults={"email": shops_admin_email})
    if _set_password_if_needed(admin, shops_admin_password, created, reset_password):
        summary["password_set"].append(SHOPS_ADMIN)
    admin.is_superuser = admin.is_staff = False
    admin.is_active = True
    admin.save()
    if created:
        summary["created"].append(SHOPS_ADMIN)

    now = timezone.now()
    for store in stores:
        other_owner = (
            StoreMembership.objects.filter(
                store=store, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE
            ).exclude(user=admin).select_related("user").first()
        )
        if other_owner is not None:
            raise AccountError(
                f"{store.slug} already has a different active owner ({other_owner.user.username}); not changing it"
            )
        membership, m_created = StoreMembership.objects.get_or_create(
            store=store, user=admin,
            defaults={"role": StoreMembership.Role.OWNER, "status": StoreMembership.MembershipStatus.ACTIVE, "accepted_at": now},
        )
        if not m_created and (
            membership.role != StoreMembership.Role.OWNER
            or membership.status != StoreMembership.MembershipStatus.ACTIVE
        ):
            membership.role = StoreMembership.Role.OWNER
            membership.status = StoreMembership.MembershipStatus.ACTIVE
            membership.accepted_at = membership.accepted_at or now
            membership.revoked_at = None
            membership.save()
        summary["memberships"].append(store.slug)
    return summary
