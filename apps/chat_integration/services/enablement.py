"""Who gets chat: OFF globally by default, ON per store only when the PLATFORM enables it (pilot stores).

The per-store switch reuses RastiSi's existing per-store integration table (``StoreIntegrationConnection``) instead of a
new configuration framework. The provider code is deliberately NOT registered in the merchant-facing integration
registry (``apps.stores.integrations.registry``), so it never appears on a merchant's integrations page: merchants cannot
switch chat on or off for themselves — only a platform superuser can (platform admin store page).

Deploying this code enables nothing: ``RASTICHAT_INTEGRATION_ENABLED`` defaults to False, and a store has no connection row
until a platform owner enables it. Rollback = switch the store off (or the global flag): the widget and every entry point
disappear immediately; RastiChat keeps the history.
"""
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.models import Store, StoreIntegrationConnection

from .. import conf
from . import tenant_service

PROVIDER_CODE = "rastichat"


class ChatEnablementError(Exception):
    pass


def get_connection(store):
    return StoreIntegrationConnection.objects.filter(store=store, provider_code=PROVIDER_CODE).first()


def chat_enabled_for_store(store) -> bool:
    """True only when ALL hold: global flag on, store active, platform enabled it for this store, tenant provisioned."""
    if store is None or not conf.globally_enabled() or store.status != Store.Status.ACTIVE:
        return False
    connection = get_connection(store)
    return bool(connection and connection.is_active and project_public_key(store))


def project_public_key(store) -> str:
    connection = get_connection(store)
    return (connection.get_credentials().get("project_public_key", "") if connection else "")


def enable_for_store(store, *, actor):
    """Provision (idempotently) the store's RastiChat tenant, THEN mark chat enabled. If RastiChat is unreachable or
    refuses, nothing is enabled — a store never ends up "enabled" without a working tenant."""
    if not conf.globally_enabled():
        raise ChatEnablementError("یکپارچه‌سازی گفتگو در سطح پلتفرم فعال نیست.")
    if store.status != Store.Status.ACTIVE:
        raise ChatEnablementError("فقط فروشگاه فعال می‌تواند گفتگو داشته باشد.")
    tenant = tenant_service.ensure_remote_tenant(store)
    connection, _ = StoreIntegrationConnection.objects.get_or_create(store=store, provider_code=PROVIDER_CODE)
    was_active = connection.is_active
    connection.set_credentials({"project_public_key": tenant["project_public_key"]})
    connection.is_active = True
    connection.connected_at = connection.connected_at or timezone.now()
    connection.save(update_fields=["encrypted_credentials", "is_active", "connected_at", "updated_at"])
    record_audit_event(
        store=store, actor=actor, action_code="chat.enabled" if not was_active else "chat.resynced",
        object_type="StoreIntegrationConnection", object_id=connection.pk, object_label="RastiChat",
    )
    return connection


def disable_for_store(store, *, actor):
    connection = get_connection(store)
    if connection is None or not connection.is_active:
        return connection
    connection.is_active = False
    connection.save(update_fields=["is_active", "updated_at"])
    record_audit_event(
        store=store, actor=actor, action_code="chat.disabled",
        object_type="StoreIntegrationConnection", object_id=connection.pk, object_label="RastiChat",
    )
    return connection
