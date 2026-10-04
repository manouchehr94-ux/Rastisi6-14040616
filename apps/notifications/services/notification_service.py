"""صف/تحویلِ اعلان‌ها (Section 16). ``enqueue`` هرگز چیزی ارسال نمی‌کند —
فقط یک ردیفِ پایدار می‌سازد؛ ``deliver_pending`` تنها جایی است که واقعاً
پیامک/ایمیل می‌فرستد (یا برایِ درون‌برنامه‌ای، صرفاً موجودیِ خودِ ردیف را
تحویل‌شده حساب می‌کند). یک خطای ارسال هرگز اعلان را از دست نمی‌دهد — فقط
``FAILED`` می‌شود و در اجرایِ بعدیِ ``deliver_pending`` دوباره تلاش
می‌شود."""

import logging
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.notifications.models import NotificationOutbox

logger = logging.getLogger(__name__)

C = NotificationOutbox.Channel
S = NotificationOutbox.Status


def enqueue(
    *, channel: str, body: str, subject: str = "", recipient_user=None, recipient_phone: str = "",
    recipient_email: str = "", store=None, is_security: bool = False, metadata: dict | None = None,
) -> NotificationOutbox:
    return NotificationOutbox.objects.create(
        channel=channel, subject=subject, body=body, recipient_user=recipient_user,
        recipient_phone=recipient_phone, recipient_email=recipient_email, store=store,
        is_security=is_security, metadata=metadata or {},
    )


BACKOFF_MINUTES = (1, 5, 30, 120, 360)
STALE_CLAIM_MINUTES = 10
_PHONE_RE = re.compile(r"09\d{9}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def sanitize_error(message: str) -> str:
    """خطایِ ارائه‌دهنده را برایِ ثبت در تاریخچه/لاگ امن می‌کند: شماره/ایمیلِ
    گیرنده ماسک و طول محدود می‌شود (اطلاعاتِ حساس در لاگ نماند)."""
    text = _PHONE_RE.sub(lambda m: m.group(0)[:4] + "*****" + m.group(0)[-2:], str(message or ""))
    text = _EMAIL_RE.sub("***@***", text)
    return text[:300]


def _store_name(notification) -> str:
    return notification.store.name if notification.store_id else "راستیسی"


def _send_email(notification: NotificationOutbox) -> str:
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    from apps.core.models import ShopSettings

    primary = "#6D28D9"
    if notification.store_id:
        try:
            primary = ShopSettings.load(store=notification.store).primary_color or primary
        except Exception:  # noqa: BLE001 — هویتِ بصری اختیاری است؛ نبودنش ارسال را نمی‌شکند
            pass
    html_body = render_to_string("notifications/email/base.html", {
        "store_name": _store_name(notification), "subject": notification.subject,
        "paragraphs": [line for line in notification.body.splitlines() if line.strip()],
        "primary_color": primary,
    })
    message = EmailMultiAlternatives(
        notification.subject, notification.body, settings.DEFAULT_FROM_EMAIL, [notification.recipient_email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
    return "email"


def _deliver_one(notification: NotificationOutbox) -> None:
    """ارسالِ واقعیِ یک اعلان. ``notification.provider``/``provider_ref`` را پر
    می‌کند (ذخیره با فراخوان است). هر خطا → استثنا."""
    if notification.channel == C.IN_APP:
        return  # خودِ ردیف تحویل است — نیازی به ارسالِ خارجی نیست.

    if notification.channel == C.SMS:
        from apps.sms.events import SmsEvent

        if notification.store_id:
            from apps.sms.services.sms_service import send_raw_sms

            log = send_raw_sms(
                phone=notification.recipient_phone, message=notification.body,
                store=notification.store, event_key=SmsEvent.NOTIFICATION,
            )
            if log is not None:
                notification.provider = log.provider or ""
                notification.provider_ref = log.provider_ref_id or ""
            if log is None or log.status != log.Status.SENT:
                raise RuntimeError(
                    log.error_message if log is not None and log.error_message else
                    "ارسال پیامک فروشگاه انجام نشد"
                )
            return

        from apps.portal.services.owner_sms_service import send_platform_sms
        from apps.sms.services.billing_policy_service import record_platform_attempt

        result = send_platform_sms(to=notification.recipient_phone, text=notification.body)
        record_platform_attempt(
            event_key=SmsEvent.NOTIFICATION, recipient=notification.recipient_phone,
            message=notification.body, result=result,
        )
        notification.provider = "platform"
        if not result.success:
            raise RuntimeError(result.error_message or "ارسالِ پیامک ناموفق بود")
        return

    if notification.channel == C.EMAIL:
        notification.provider = _send_email(notification)
        return

    raise RuntimeError(f"کانالِ ناشناخته: {notification.channel}")


def _claim_batch(limit: int, now) -> list[NotificationOutbox]:
    """ردیف‌هایِ آماده را اتمیک برمی‌دارد (SENDING) تا دو کارگرِ همزمان یک
    اعلان را دوبار نفرستند. ردیف‌هایِ SENDINGِ کهنه (کارگرِ مرده) دوباره برداشته می‌شوند."""
    stale = now - timedelta(minutes=STALE_CLAIM_MINUTES)
    with transaction.atomic():
        qs = (
            NotificationOutbox.objects.select_for_update(skip_locked=True)
            .filter(sms_log__isnull=True)  # آینه‌های تاریخچه‌ی پیامکِ قدیمی هرگز ارسال نمی‌شوند
            .exclude(metadata__has_key="legacy_sms_log_id")
            .filter(attempts__lt=F("max_attempts"))
            .filter(
                Q(status=S.PENDING) | Q(status=S.FAILED) | Q(status=S.SENDING, claimed_at__lt=stale)
            )
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .order_by("created_at")
        )
        rows = list(qs[:limit])
        if rows:
            NotificationOutbox.objects.filter(pk__in=[r.pk for r in rows]).update(status=S.SENDING, claimed_at=now)
    return rows


def _anchor_delivery_validity(notification: NotificationOutbox) -> None:
    """کدهایِ دارایِ «اعتبار از تحویل»: با اولین ارسالِ موفقِ اعلان، انقضا از همان لحظه
    محاسبه می‌شود (یک‌بار؛ ارسال‌هایِ بعدیِ کانالِ دیگر تغییری نمی‌دهند)."""
    meta = notification.metadata or {}
    days, coupon_id = meta.get("valid_days_from_delivery"), meta.get("coupon_id")
    if not days or not coupon_id:
        return
    from apps.cart.models import Coupon

    now = notification.sent_at or timezone.now()
    Coupon.objects.filter(pk=coupon_id, delivery_anchored_at__isnull=True).update(
        delivery_anchored_at=now, expires_at=now + timedelta(days=days),
    )


def _consent_withdrawn(notification: NotificationOutbox) -> bool:
    """پیامِ تبلیغاتیِ صف‌شده برایِ مشتری: اگر رضایتِ کانال تا لحظه‌ی ارسال پس گرفته شده (یا هرگز ثبت نبوده)
    ارسال نمی‌شود. پیام‌هایِ تراکنشی/امنیتی/کارکنان و ارسال‌هایِ آزمایشی تأثیری نمی‌پذیرند."""
    if not (notification.is_promotional and notification.customer_id) or notification.is_test:
        return False
    from apps.customers.services.consent_service import fresh_promotional_consent

    return not fresh_promotional_consent(notification.customer_id, notification.channel)


def _process(notification: NotificationOutbox, now) -> bool | None:
    """یک اعلانِ برداشته‌شده (SENDING) را می‌فرستد و وضعیتش را ذخیره می‌کند.
    → ``True`` اگر ارسال موفق بود، ``False`` اگر شکست خورد، ``None`` اگر به‌دلیلِ نبودِ رضایت ارسال نشد."""
    if _consent_withdrawn(notification):
        notification.status = S.SKIPPED
        notification.skip_reason = "consent_withdrawn"
        notification.claimed_at = None
        notification.next_attempt_at = None
        notification.save(update_fields=["status", "skip_reason", "claimed_at", "next_attempt_at", "updated_at"])
        return None
    notification.attempts += 1
    ok = True
    try:
        _deliver_one(notification)
    except Exception as exc:  # noqa: BLE001 — یک اعلانِ خراب نباید بقیه‌ی صف را متوقف کند
        ok = False
        notification.last_error = sanitize_error(exc)
        if notification.attempts >= notification.max_attempts:
            notification.status = S.DEAD
            notification.next_attempt_at = None
        else:
            notification.status = S.FAILED
            delay = BACKOFF_MINUTES[min(notification.attempts - 1, len(BACKOFF_MINUTES) - 1)]
            notification.next_attempt_at = now + timedelta(minutes=delay)
        logger.warning("notification %s failed (attempt %s): %s", notification.pk, notification.attempts, notification.last_error)
    else:
        notification.status = S.SENT
        notification.sent_at = timezone.now()
        notification.last_error = ""
        notification.next_attempt_at = None
        _anchor_delivery_validity(notification)
    notification.claimed_at = None
    notification.save(update_fields=[
        "status", "attempts", "sent_at", "last_error", "next_attempt_at", "claimed_at",
        "provider", "provider_ref", "updated_at",
    ])
    return ok


def deliver_pending(*, limit: int = 200, now=None) -> dict:
    now = now or timezone.now()
    sent = failed = skipped = 0
    for notification in _claim_batch(limit, now):
        outcome = _process(notification, now)
        if outcome is None:
            skipped += 1
        elif outcome:
            sent += 1
        else:
            failed += 1
    return {"processed": sent + failed + skipped, "sent": sent, "failed": failed, "skipped": skipped}


def deliver_single(notification: NotificationOutbox, *, now=None) -> NotificationOutbox:
    """ارسالِ فوریِ یک اعلانِ مشخص (ارسالِ آزمایشی/تلاشِ دستی) — فقط اگر هنوز
    ``PENDING``/``FAILED`` باشد؛ برداشتِ اتمیک مانعِ ارسالِ دوباره‌ی همزمان است."""
    now = now or timezone.now()
    if notification.is_legacy_sms_mirror:
        return notification
    claimed = NotificationOutbox.objects.filter(
        pk=notification.pk, status__in=(S.PENDING, S.FAILED), attempts__lt=F("max_attempts"),
    ).update(status=S.SENDING, claimed_at=now)
    notification.refresh_from_db()
    if claimed:
        _process(notification, now)
    return notification


class RetryNotAllowed(Exception):
    """این اعلان قابلِ تلاشِ دستی نیست (مثلاً به‌دلیلِ نبودِ رضایت ارسال نشده)."""


def retry_notification(notification: NotificationOutbox) -> NotificationOutbox:
    """تلاشِ دستیِ مدیر: فقط ``FAILED``/``DEAD``. اعلانِ ``SKIPPED`` (نبودِ رضایت،
    گیرنده‌ی نامعتبر…) عمداً قابلِ تلاشِ دوباره نیست."""
    if notification.is_legacy_sms_mirror:
        raise RetryNotAllowed("این پیامک از مسیرِ قدیمیِ پیامک ارسال شده؛ تلاشِ دوباره از «گزارشِ پیامک‌ها» انجام می‌شود.")
    if notification.status not in (S.FAILED, S.DEAD):
        raise RetryNotAllowed("فقط اعلان‌هایِ ناموفق قابلِ تلاشِ دوباره‌اند.")
    notification.status = S.PENDING
    notification.next_attempt_at = None
    notification.claimed_at = None
    notification.max_attempts = max(notification.max_attempts, notification.attempts + 1)
    notification.save(update_fields=["status", "next_attempt_at", "claimed_at", "max_attempts", "updated_at"])
    return notification


def notify_security_event(
    *, subject: str, body: str, user=None, phone: str = "", store=None, metadata: dict | None = None,
) -> list[NotificationOutbox]:
    """اعلانِ امنیتی — بدونِ هیچ مسیرِ opt-out. اگر ``user`` داده شود یک
    اعلانِ درون‌برنامه‌ای، و اگر ``phone`` داده شود یک پیامک، صف می‌شود."""
    created = []
    if user is not None:
        created.append(enqueue(
            channel=C.IN_APP, subject=subject, body=body, recipient_user=user,
            store=store, is_security=True, metadata=metadata,
        ))
    if phone:
        created.append(enqueue(
            channel=C.SMS, body=body, recipient_phone=phone, store=store, is_security=True, metadata=metadata,
        ))
    return created
