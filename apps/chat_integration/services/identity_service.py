"""RastiSi identities -> RastiChat assertions (Contract v1 §7). Every claim is derived from server-side state:

* customer  — the authenticated ``Customer`` of the request's Host-resolved store;
* staff     — an ACTIVE ``StoreMembership`` of the store resolved from the ADMIN host (never a form field);
* platform  — ``is_staff and is_superuser`` (the platform owner semantics RastiSi already has; no new support role).

RastiChat only ever sees generic roles (owner|admin|operator) — never RastiSi role names.
"""
from apps.stores.models import StoreMembership

from .. import client
from . import tenant_service

Role = StoreMembership.Role

# Which RastiSi membership roles may use which chat surface. Deliberately NOT added to apps.stores.authorization's
# permission matrix (that matrix is exhaustively tested and must not change for this feature); chat access is derived
# from the same authoritative ACTIVE membership, with the minimal role sets below.
CUSTOMER_CHAT_ROLES = {Role.OWNER: "owner", Role.ADMINISTRATOR: "admin", Role.ORDER_MANAGER: "operator"}
PLATFORM_SUPPORT_ROLES = {Role.OWNER: "owner", Role.ADMINISTRATOR: "admin"}


def external_user_id(user) -> str:
    return f"u{user.pk}"


def display_name(user) -> str:
    owner_profile = getattr(user, "owner_profile", None)
    name = getattr(owner_profile, "full_name", "") if owner_profile else ""
    return (name or user.get_full_name() or f"کاربر {user.pk}")[:255]


def customer_assertion(*, store, customer, origin: str) -> str:
    return client.make_assertion(
        actor="customer", sub=f"c{customer.pk}", tenant=tenant_service.external_tenant_id(store),
        name=customer.full_name, origin=origin,
    )


def staff_role_for(membership, *, surface: str):
    table = CUSTOMER_CHAT_ROLES if surface == "customers" else PLATFORM_SUPPORT_ROLES
    return table.get(membership.role) if membership is not None else None


def staff_assertion(*, store, user, role: str) -> str:
    return client.make_assertion(
        actor="tenant_staff", sub=external_user_id(user), tenant=tenant_service.external_tenant_id(store),
        role=role, name=display_name(user),
    )


def platform_assertion(*, user) -> str:
    return client.make_assertion(actor="platform_staff", sub=external_user_id(user), role="owner", name=display_name(user))
