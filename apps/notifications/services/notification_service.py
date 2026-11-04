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


class SenderNotActiveError(Exception):
    """This Store has no ACTIVE verified-domain sender right now — block ONLY the email channel."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(f"sender identity not active: {reason_code}")


class RecipientSuppressedError(Exception):
    """The recipient previously bounced hard / complained — never retried automatically."""


def _is_platform_sender(notification: NotificationOutbox) -> bool:
    from apps.notifications import events as ev

    if not notification.store_id:
        return True
    event = ev.EVENTS.get(notification.event_key)
    return event is not None and event.sender == "platform"


def _store_sender_address(notification: NotificationOutbox) -> str:
    """Mandatory custom-domain policy: a Store's customer/staff email is sent ONLY from its own verified
    domain. ``platform.*`` events (sender="platform") are the one exception by design: they are RastiSi's own
    notice TO the store admin (e.g. "your email sending just broke"), so they must keep working even when the
    Store's own domain is the thing that's broken — those use ``settings.DEFAULT_FROM_EMAIL``, never the
    Store's domain, and never substitute for a Store→customer send."""
    from django.conf import settings

    from apps.notifications import events as ev
    from apps.notifications.mail.provisioning_service import active_sender_address

    if not notification.store_id:
        return settings.DEFAULT_FROM_EMAIL  # platform-originated (e.g. staff/security without a Store)
    event = ev.EVENTS.get(notification.event_key)
    if event is not None and event.sender == "platform":
        return settings.DEFAULT_FROM_EMAIL
    return active_sender_address(notification.store)


def _is_suppressed(notification: NotificationOutbox) -> bool:
    if not notification.store_id or not notification.recipient_email:
        return False
    from apps.notifications.models import EmailSuppression

    return EmailSuppression.objects.filter(
        store_id=notification.store_id, email__iexact=notification.recipient_email,
    ).exists()


def _send_email(notification: NotificationOutbox) -> str:
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    from apps.core.models import ShopSettings
    from apps.notifications.mail.registry import get_transport
    from apps.notifications.mail.base import OutboundEmail, TransportNotConfigured

    if _is_suppressed(notification):
        raise RecipientSuppressedError(notification.recipient_email)

    sender = _store_sender_address(notification)
    if not sender:
        raise SenderNotActiveError("sender_not_active")

    from apps.notifications.services import template_service

    html_body = template_service.render_email_document(
        notification.store if notification.store_id else None, notification.subject, notification.body,
        notification.html_body,
    )

    if _is_platform_sender(notification):
        # platform-originated mail (no Store sender concept) keeps using Django's own EMAIL_BACKEND,
        # exactly as before this feature existed (console backend in dev, real SMTP in production).
        from django.conf import settings as dj_settings

        message = EmailMultiAlternatives(
            notification.subject, notification.body, dj_settings.DEFAULT_FROM_EMAIL, [notification.recipient_email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
        notification.sender_address = dj_settings.DEFAULT_FROM_EMAIL
        return "email"

    try:
        transport = get_transport()
    except TransportNotConfigured as exc:
        raise RuntimeError(str(exc)) from exc

    outcome = transport.send(OutboundEmail(
        from_address=sender, from_name=_store_name(notification), to_address=notification.recipient_email,
        subject=notification.subject, text_body=notification.body, html_body=html_body,
        tags={"event_key": notification.event_key or "", "store_id": str(notification.store_id or "")},
    ))
    notification.sender_address = sender
    notification.provider_ref = outcome.message_id
    if not outcome.ok:
        if not outcome.retryable:
            notification.metadata = {**(notification.metadata or {}), "permanent_send_error": outcome.error_code}
        raise RuntimeError(outcome.error or outcome.error_code or "ارسال ایمیل ناموفق بود")
    return transport.code


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


REVIVE_EXPIRED_WITHIN_DAYS = 7


def release_held(store) -> dict:
    """Recovery when a Store's sender becomes ACTIVE: held rows are released for immediate sending, and important
    (non-promotional) rows that expired in the last 7 days because of sender/rate problems are revived. Promotional
    rows that expired are NOT revived (stale marketing). Idempotent; never sends by itself."""
    base = NotificationOutbox.objects.filter(store=store, channel=C.EMAIL)
    released = base.filter(status=S.PENDING, held_since__isnull=False).update(
        next_attempt_at=None, held_since=None, last_error="",
    )
    revived = base.filter(
        status=S.DEAD, is_promotional=False, last_error__endswith="_expired",
        created_at__gte=timezone.now() - timedelta(days=REVIVE_EXPIRED_WITHIN_DAYS),
    ).update(status=S.PENDING, next_attempt_at=None, held_since=None, last_error="")
    return {"released": released, "revived": revived}


_GATE_OPEN = object()
HELD = "held"
HOLD_RETRY_MINUTES = 15


def _finish_skipped(notification: NotificationOutbox, reason: str):
    notification.status = S.SKIPPED
    notification.skip_reason = reason
    notification.claimed_at = None
    notification.next_attempt_at = None
    notification.save(update_fields=["status", "skip_reason", "claimed_at", "next_attempt_at", "attempts", "updated_at"])
    return None


def _hold(notification: NotificationOutbox, now, reason: str):
    """Email cannot go out RIGHT NOW (no active sender / rate limit) but may soon: keep the row, do not burn a
    retry attempt, give up (SKIPPED, visible in history) after ``RASTISI_EMAIL_HOLD_MAX_HOURS``."""
    from django.conf import settings

    from apps.notifications import events as ev

    notification.held_since = notification.held_since or now
    event = ev.EVENTS.get(notification.event_key)
    important = not notification.is_promotional and (event is None or event.category in (ev.TRANSACTIONAL, ev.SECURITY))
    hours = (getattr(settings, "RASTISI_EMAIL_HOLD_MAX_HOURS", 72) if important
             else getattr(settings, "RASTISI_EMAIL_HOLD_MAX_HOURS_PROMOTIONAL", 24))
    if now - notification.held_since > timedelta(hours=hours):
        if not important:
            return _finish_skipped(notification, f"{reason}_expired")  # promotional: expiry by design, visible as SKIPPED
        # Transactional / security: NEVER silently discarded. It becomes a visible DEAD row ("failed — needs action"),
        # listed in history/failures, manually retryable, and auto-revived by release_held() when the sender recovers.
        notification.status = S.DEAD
        notification.claimed_at = None
        notification.next_attempt_at = None
        notification.last_error = f"{reason}_expired"
        notification.save(update_fields=["status", "claimed_at", "next_attempt_at", "last_error", "held_since", "updated_at"])
        return False
    notification.status = S.PENDING
    notification.claimed_at = None
    notification.next_attempt_at = now + timedelta(minutes=HOLD_RETRY_MINUTES)
    notification.last_error = reason
    notification.save(update_fields=["status", "claimed_at", "next_attempt_at", "last_error", "held_since", "attempts", "updated_at"])
    return HELD


def _rate_limited(notification: NotificationOutbox, now) -> bool:
    """Tenant-level (per store per hour) and platform-level (per minute) caps — counted from the persistent outbox
    so the limit holds across workers/processes."""
    from django.conf import settings

    sent = NotificationOutbox.objects.filter(channel=C.EMAIL, status=S.SENT)
    store_cap = getattr(settings, "RASTISI_EMAIL_STORE_HOURLY_LIMIT", 0)
    if store_cap and notification.store_id and not notification.is_security:
        if sent.filter(store_id=notification.store_id, sent_at__gte=now - timedelta(hours=1)).count() >= store_cap:
            return True
    platform_cap = getattr(settings, "RASTISI_EMAIL_PLATFORM_MINUTE_LIMIT", 0)
    if platform_cap and sent.filter(sent_at__gte=now - timedelta(minutes=1)).count() >= platform_cap:
        return True
    return False


def _email_gate(notification: NotificationOutbox, now):
    """Decide BEFORE spending an attempt: suppressed → skip; no active store sender / over rate limit → hold."""
    if _is_suppressed(notification):
        return _finish_skipped(notification, "recipient_suppressed")
    if not _is_platform_sender(notification) and not _store_sender_address(notification):
        return _hold(notification, now, "sender_not_active")
    if _rate_limited(notification, now):
        return _hold(notification, now, "rate_limited")
    return _GATE_OPEN


def _process(notification: NotificationOutbox, now) -> bool | None:
    """یک اعلانِ برداشته‌شده (SENDING) را می‌فرستد و وضعیتش را ذخیره می‌کند.
    → ``True`` اگر ارسال موفق بود، ``False`` اگر شکست خورد، ``None`` اگر ارسال نشد (رضایت/سرکوب)،
    ``HELD`` اگر موقتاً نگه داشته شد (فرستنده‌ی غیرفعال / سقفِ نرخ) — بدونِ مصرفِ تلاش."""
    if _consent_withdrawn(notification):
        notification.status = S.SKIPPED
        notification.skip_reason = "consent_withdrawn"
        notification.claimed_at = None
        notification.next_attempt_at = None
        notification.save(update_fields=["status", "skip_reason", "claimed_at", "next_attempt_at", "updated_at"])
        return None
    if notification.channel == C.EMAIL:
        gate = _email_gate(notification, now)
        if gate is not _GATE_OPEN:
            return gate
    notification.attempts += 1
    ok = True
    try:
        _deliver_one(notification)
    except RecipientSuppressedError:
        return _finish_skipped(notification, "recipient_suppressed")
    except SenderNotActiveError as exc:  # raced with a status change between gate and send: hold, don't burn an attempt
        notification.attempts -= 1
        return _hold(notification, now, exc.reason_code)
    except Exception as exc:  # noqa: BLE001 — یک اعلانِ خراب نباید بقیه‌ی صف را متوقف کند
        ok = False
        notification.last_error = sanitize_error(exc)
        if (notification.metadata or {}).get("permanent_send_error"):
            notification.status = S.DEAD  # the provider said it will never succeed (e.g. rejected sender): do not retry
            notification.next_attempt_at = None
        elif notification.attempts >= notification.max_attempts:
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
        "provider", "provider_ref", "metadata", "sender_address", "updated_at",
    ])
    return ok


def deliver_pending(*, limit: int = 200, now=None) -> dict:
    now = now or timezone.now()
    sent = failed = skipped = held = 0
    for notification in _claim_batch(limit, now):
        outcome = _process(notification, now)
        if outcome is None:
            skipped += 1
        elif outcome == HELD:
            held += 1
        elif outcome:
            sent += 1
        else:
            failed += 1
    return {"processed": sent + failed + skipped + held, "sent": sent, "failed": failed, "skipped": skipped, "held": held}


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
    notification.held_since = None
    notification.max_attempts = max(notification.max_attempts, notification.attempts + 1)
    meta = dict(notification.metadata or {})
    meta.pop("permanent_send_error", None)  # operational recovery: let a DEAD row be re-attempted after the cause is fixed
    notification.metadata = meta
    notification.save(update_fields=["status", "next_attempt_at", "claimed_at", "held_since", "max_attempts", "metadata", "updated_at"])
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
