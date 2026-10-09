"""Best-effort lifecycle hooks (RastiSi -> RastiChat). They never raise into the caller and do nothing unless chat is
switched on for the store: losing RastiChat for a moment must never break a RastiSi action. ``manage.py chat_sync_tenants``
reconciles anything a failed hook missed (idempotent)."""
import logging

from django.db import transaction

from .. import client, conf
from . import enablement, identity_service, tenant_service

logger = logging.getLogger(__name__)


def _safe(label, fn):
    """Run `fn` after the surrounding transaction commits (never a network call inside a DB transaction, never for a
    rolled-back change), swallowing every failure."""
    def run():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a hook must never break the RastiSi operation that triggered it
            logger.warning("rastichat_hook_failed hook=%s error=%s", label, type(exc).__name__)

    transaction.on_commit(run)


def store_status_changed(store):
    if not conf.globally_enabled() or enablement.get_connection(store) is None:
        return
    _safe("store_status", lambda: client.set_tenant_status(
        tenant_service.external_tenant_id(store), "active" if store.status == "active" else "suspended"))


def membership_removed(membership):
    """Staff membership revoked / role changed away from chat roles: cut chat access now (RastiChat also closes their live sockets)."""
    store = membership.store
    if not conf.globally_enabled() or enablement.get_connection(store) is None:
        return
    _safe("membership_removed", lambda: client.remove_staff_member(
        tenant_service.external_tenant_id(store), identity_service.external_user_id(membership.user, store)))


def user_suspended(user):
    if not conf.globally_enabled():
        return
    from apps.stores.models import StoreMembership
    # a person holds one RastiChat identity per store (plus a platform one): cut them all
    ids = {identity_service.external_user_id(user)}
    for store in {m.store for m in StoreMembership.objects.filter(user=user).select_related("store")}:
        ids.add(identity_service.external_user_id(user, store))
    for external_id in sorted(ids):
        _safe("user_suspended", lambda external_id=external_id: client.disable_staff_user(external_id))
