"""حذفِ فروشگاه (Section 14) — همیشه نرم، هرگز فوری، هرگز بدونِ تأییدِ
تایپی و OTP گام‌دوم (action=``store_delete``، در لایه‌ی ویو).

قاعده‌ی مطلق: ``request_deletion`` هرگز داده‌ای پاک نمی‌کند — فقط
``status`` را به ``CLOSED`` می‌برد (پس فروشگاه بلافاصله غیرِ عمومی می‌شود
— ``publication_service``) و یک تاریخِ پاک‌سازیِ نهاییِ آینده برنامه‌ریزی
می‌کند (پیکربندی‌پذیر، ۱۸۰ تا ۳۶۵ روز — ``PlatformConfiguration.
deletion_retention_days``). پاک‌سازیِ واقعی فقط از طریقِ دستورِ مدیریتیِ
``purge_deleted_stores`` و فقط پس از رسیدنِ آن تاریخ رخ می‌دهد."""

from django.db import transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.portal.services.platform_config_service import get_platform_configuration, record_platform_audit_event
from apps.stores.models import Store


class DeletionError(Exception):
    """خطای قابل‌نمایشِ درخواست/لغوِ حذفِ فروشگاه."""


@transaction.atomic
def request_deletion(*, store: Store, actor, typed_confirmation: str) -> Store:
    """تأییدِ تایپی: مالک باید دقیقاً اسلاگِ فروشگاه را تایپ کند — یک
    کلیکِ ساده کافی نیست (مطابقِ الگویِ رایجِ «type to confirm»)."""
    locked = Store.objects.select_for_update().get(pk=store.pk)
    if locked.deletion_requested_at is not None:
        raise DeletionError("درخواستِ حذفِ این فروشگاه از قبل ثبت شده است.")
    if (typed_confirmation or "").strip() != locked.slug:
        raise DeletionError("متنِ تایپ‌شده با اسلاگِ فروشگاه یکسان نیست.")

    config = get_platform_configuration()
    now = timezone.now()
    locked.pre_deletion_status = locked.status
    locked.status = Store.Status.CLOSED
    locked.deletion_requested_at = now
    locked.deletion_requested_by = actor
    locked.deletion_scheduled_purge_at = now + timezone.timedelta(days=config.deletion_retention_days)
    locked.save(update_fields=[
        "pre_deletion_status", "status", "deletion_requested_at", "deletion_requested_by",
        "deletion_scheduled_purge_at", "updated_at",
    ])

    record_audit_event(
        store=locked, actor=actor, action_code="store.deletion_requested",
        object_type="Store", object_id=locked.pk, object_label=locked.name,
        after={"scheduled_purge_at": str(locked.deletion_scheduled_purge_at)},
    )
    _notify_deletion_requested(store=locked, actor=actor)
    return locked


def _notify_deletion_requested(*, store: Store, actor) -> None:
    from apps.notifications.services.notification_service import notify_security_event

    phone = getattr(getattr(actor, "owner_profile", None), "phone", "")
    from apps.core.jalali_utils import format_jalali
    from apps.core.utils import to_fa_digits

    # FOLLOWUP-14: human-facing dates are Jalali (the stored instant stays UTC/aware).
    purge_date = to_fa_digits(format_jalali(store.deletion_scheduled_purge_at)) if store.deletion_scheduled_purge_at else ""
    notify_security_event(
        subject="درخواستِ حذفِ فروشگاه ثبت شد",
        body=f"درخواستِ حذفِ فروشگاهِ «{store.name}» ثبت شد. اگر این درخواست را شما نداده‌اید، فوراً وارد "
             f"حسابِ خود شوید و آن را لغو کنید. این فروشگاه تا {purge_date} برایِ همیشه پاک خواهد شد.",
        user=actor, phone=phone, store=store,
    )


@transaction.atomic
def cancel_deletion(*, store: Store, actor) -> Store:
    """درخواستِ حذف را لغو می‌کند و وضعیتِ فروشگاه را به دقیقاً همان وضعیتِ
    پیش از درخواست برمی‌گرداند — بدونِ نیازِ OTP گام‌دوم (بازگرداندنِ ایمنی
    است، نه اقدامی حساس)."""
    locked = Store.objects.select_for_update().get(pk=store.pk)
    if locked.deletion_requested_at is None:
        raise DeletionError("درخواستِ حذفی برایِ لغو وجود ندارد.")

    restored_status = locked.pre_deletion_status or Store.Status.ACTIVE
    locked.status = restored_status
    locked.deletion_requested_at = None
    locked.deletion_requested_by = None
    locked.deletion_scheduled_purge_at = None
    locked.pre_deletion_status = ""
    locked.save(update_fields=[
        "status", "deletion_requested_at", "deletion_requested_by",
        "deletion_scheduled_purge_at", "pre_deletion_status", "updated_at",
    ])

    record_audit_event(
        store=locked, actor=actor, action_code="store.deletion_cancelled",
        object_type="Store", object_id=locked.pk, object_label=locked.name,
    )
    return locked


def stores_due_for_purge():
    return Store.objects.filter(
        deletion_requested_at__isnull=False, deletion_scheduled_purge_at__lte=timezone.now(),
    )


def purge_due_stores(*, dry_run: bool = True, actor=None) -> list[dict]:
    """فروشگاه‌هایی که تاریخِ پاک‌سازی‌شان رسیده را (در حالتِ واقعی) برایِ
    همیشه حذف می‌کند — ``Store.delete()`` واقعی، با تمامِ CASCADEهایِ
    تعریف‌شده در طرحِ دیتابیس. هر فروشگاه در تراکنشِ اتمیکِ خودش پردازش
    می‌شود — شکستِ یک فروشگاه (مثلاً به‌خاطرِ یک ارجاعِ PROTECT پیش‌بینی‌نشده)
    بقیه‌ی دسته را متوقف نمی‌کند. رخدادِ حسابرسی «پیش از حذف» ثبت می‌شود
    (نه بعد — چون ``AuditLogEntry.store`` با CASCADE به خودِ Store وابسته
    است و با حذفِ Store از بین می‌رود)، در ``PlatformAuditLogEntry`` که
    Store-owned نیست."""
    results = []
    for store in stores_due_for_purge():
        row = {
            "store_id": store.pk, "slug": store.slug, "name": store.name,
            "platform_code": store.platform_code, "purged": False, "error": None,
        }
        if dry_run:
            results.append(row)
            continue

        try:
            with transaction.atomic():
                record_platform_audit_event(
                    actor=actor, action_code="store.purged",
                    object_type="Store", object_id=store.pk, object_label=store.name,
                    metadata={
                        "slug": store.slug, "platform_code": store.platform_code,
                        "deletion_requested_at": str(store.deletion_requested_at),
                    },
                )
                store.delete()
            row["purged"] = True
        except Exception as exc:  # noqa: BLE001 — یک فروشگاهِ خراب نباید کلِ دسته را متوقف کند
            row["error"] = str(exc)
        results.append(row)
    return results
