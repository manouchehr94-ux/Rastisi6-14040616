"""فعال/تعلیقِ یک Store توسطِ مدیرِ پلتفرم — نگاه کنید به Platform Owner
Admin (بخشِ ۵). این‌جا هیچ داده‌ای پاک نمی‌شود و ``Store.status`` تنها
نشانه‌ی «تعلیق‌شده» نیست — ``suspended_at``/``suspended_by``/
``suspension_reason`` جدا نگه داشته می‌شوند تا حتی پس از فعال‌سازیِ دوباره
هم تاریخچه‌ی تعلیق در دسترس بماند."""

from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.stores.models import Store


class StoreStatusError(Exception):
    """خطای قابل‌نمایش هنگامِ تغییرِ وضعیتِ یک Store."""


def _notify_chat(store: Store) -> None:
    # RastiChat adapter (best effort, after commit, no-op unless chat is enabled for this store)
    from apps.chat_integration.services import hooks

    hooks.store_status_changed(store)


def suspend_store(store: Store, *, actor, reason: str, note: str = "") -> Store:
    if not reason.strip():
        raise StoreStatusError("دلیلِ تعلیق الزامی است.")
    if store.status == Store.Status.SUSPENDED:
        raise StoreStatusError("این فروشگاه از قبل تعلیق شده است.")

    before_status = store.status
    store.status = Store.Status.SUSPENDED
    store.suspended_at = timezone.now()
    store.suspended_by = actor
    store.suspension_reason = reason.strip()
    store.save(update_fields=["status", "suspended_at", "suspended_by", "suspension_reason", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="platform_admin.store_suspended",
        object_type="Store", object_id=store.pk, object_label=store.name,
        before={"status": before_status}, after={"status": store.status},
        metadata={"reason": reason.strip(), "note": note.strip()} if note.strip() else {"reason": reason.strip()},
    )
    _notify_chat(store)
    return store


def activate_store(store: Store, *, actor) -> Store:
    if store.status != Store.Status.SUSPENDED:
        raise StoreStatusError("این فروشگاه در حالتِ تعلیق نیست.")

    store.status = Store.Status.ACTIVE
    store.save(update_fields=["status", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="platform_admin.store_activated",
        object_type="Store", object_id=store.pk, object_label=store.name,
        before={"status": Store.Status.SUSPENDED}, after={"status": store.status},
    )
    _notify_chat(store)
    return store
