"""آینه‌ی تاریخچه‌ی پیامکِ قدیمی در ``NotificationOutbox`` (S0).

ارسالِ پیامکِ قدیمی همچنان همزمان و فقط توسطِ ``apps.sms`` انجام می‌شود و
``SmsLog`` (حسابداریِ اعتبار/هزینه) دست‌نخورده می‌ماند. این ماژول فقط بعد از
پایانِ ارسال یک ردیفِ **فقط‌تاریخچه** می‌سازد/به‌روز می‌کند تا تاریخچه‌یِ اعلان‌ها
همه‌ی پیام‌ها را نشان دهد. تضمین‌ها:

* idempotent: ``sms_log`` یکتا (OneToOne) + ``dedupe_key = legacy_sms:<id>``؛
  پردازشِ تکراری هرگز ردیفِ دوم نمی‌سازد، فقط وضعیت را همگام می‌کند.
* هرگز ارسال نمی‌کند: ردیف‌هایِ آینه ``DEAD``/``SENT`` با ``attempts == max_attempts``
  هستند و کارگر/تلاشِ دستی آن‌ها را نادیده می‌گیرد (``is_legacy_sms_mirror``).
* فقط رویدادهایِ دارایِ معادلِ جدید (``legacy_sms_event``)؛ OTP، رویدادهایِ پلتفرم و
  پیامِ خامِ ``notification`` (که خودش از outbox می‌آید) آینه نمی‌شوند — وگرنه
  پیامکِ سیستمِ جدید دوبار در تاریخچه می‌آمد.
* هر خطا در آینه‌سازی لاگ می‌شود و هرگز ارسال/لاگِ پیامک را نمی‌شکند."""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction

from apps.notifications import events as ev
from apps.notifications.models import NotificationOutbox

logger = logging.getLogger(__name__)
S = NotificationOutbox.Status


def _customer_for(phone: str):
    from apps.customers.models import Customer

    return Customer.objects.filter(phone=phone).first() if phone else None


def _order_for(store, context):
    code = (context or {}).get("order_code")
    if not code:
        return None
    from apps.orders.models import Order

    return Order.objects.filter(store=store, code=str(code)).first()


def _fields(log, event, *, context, is_test) -> dict:
    from apps.notifications.services.notification_service import sanitize_error

    sent = log.status == log.Status.SENT
    attempts = max(log.attempt_count, 1)
    return dict(
        channel=NotificationOutbox.Channel.SMS, store_id=log.store_id, event_key=event.key, body=log.message,
        recipient_phone=log.recipient, status=S.SENT if sent else S.DEAD, attempts=attempts, max_attempts=attempts,
        sent_at=log.sent_at if sent else None, last_error="" if sent else sanitize_error(log.error_message),
        provider=log.provider or "", provider_ref=log.provider_ref_id or "", next_attempt_at=None, claimed_at=None,
        is_test=is_test, is_promotional=False, is_security=False,
        metadata={
            "legacy_sms_log_id": log.pk, "billable_units": log.billable_units, "cost_toman": log.cost_toman,
        },
    )


def record_legacy_sms(log, *, context=None, is_test=False, resolve_links=True):
    """→ ردیفِ آینه یا ``None`` (غیرقابل‌آینه). فراخوانیِ مکرر امن است."""
    if log is None or not log.store_id or log.status not in (log.Status.SENT, log.Status.FAILED):
        return None
    event = ev.event_for_legacy_sms(log.event_key)
    if event is None:
        return None
    fields = _fields(log, event, context=context, is_test=is_test)
    dedupe = f"legacy_sms:{log.pk}"
    try:
        with transaction.atomic():
            row = NotificationOutbox.objects.filter(sms_log=log).first()
            created = row is None
            if created:
                extra = {}
                if resolve_links:
                    extra = {"customer": _customer_for(log.recipient), "order": _order_for(log.store, context)}
                    extra["recipient_user"] = getattr(extra["customer"], "user", None) if extra["customer"] else None
                row = NotificationOutbox.objects.create(sms_log=log, dedupe_key=dedupe, **fields, **extra)
            else:
                # همگام‌سازیِ وضعیت پس از تلاشِ دوباره‌ی قدیمی؛ فیلدهایِ لینک/آزمایشی دست‌نخورده
                for key in ("status", "attempts", "max_attempts", "sent_at", "last_error", "provider",
                            "provider_ref", "body", "metadata"):
                    setattr(row, key, fields[key])
                row.save(update_fields=[
                    "status", "attempts", "max_attempts", "sent_at", "last_error", "provider",
                    "provider_ref", "body", "metadata", "updated_at",
                ])
            if created:  # تاریخچه باید زمانِ واقعیِ پیامک را نشان دهد (مهم در backfill)
                NotificationOutbox.objects.filter(pk=row.pk).update(created_at=log.created_at)
                row.created_at = log.created_at
            return row
    except IntegrityError:  # رقابتِ دو فراخوانِ همزمان — دیگری ساخته است
        return NotificationOutbox.objects.filter(sms_log=log).first()


def safe_record_legacy_sms(log, **kwargs):
    try:
        return record_legacy_sms(log, **kwargs)
    except Exception:  # noqa: BLE001 — آینه‌ی تاریخچه هرگز نباید پیامک را بشکند
        logger.exception("legacy SMS history mirror failed for SmsLog %s", getattr(log, "pk", None))
        return None


def backfill(*, store=None, batch_size: int = 500, dry_run: bool = False, limit: int | None = None) -> dict:
    """ساختِ آینه برایِ ``SmsLog``هایِ تاریخی که هنوز ندارند. idempotent و دسته‌ای."""
    from apps.sms.models import SmsLog

    legacy_keys = [e.legacy_sms_event for e in ev.EVENTS.values() if e.legacy_sms_event]
    qs = SmsLog.objects.filter(
        store__isnull=False, event_key__in=legacy_keys, status__in=(SmsLog.Status.SENT, SmsLog.Status.FAILED),
        notification_mirror__isnull=True,
    ).select_related("store").order_by("pk")
    if store is not None:
        qs = qs.filter(store=store)
    stats = {"candidates": 0, "created": 0}
    last_pk = 0
    while True:
        chunk = list(qs.filter(pk__gt=last_pk)[:batch_size])
        if not chunk:
            break
        for log in chunk:
            last_pk = log.pk
            stats["candidates"] += 1
            if dry_run:
                continue
            # SmsLog قدیمی context ندارد؛ لینکِ مشتری/سفارش بازسازی نمی‌شود (حدس‌زدن ممنوع)
            if record_legacy_sms(log, resolve_links=False) is not None:
                stats["created"] += 1
        if limit and stats["candidates"] >= limit:
            break
    return stats
