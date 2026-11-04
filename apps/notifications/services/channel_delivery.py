"""کارگرِ تحویلِ کانال‌هایِ بیرونی (Web Push / ایمیل / موبایل) از روی ``NotificationDelivery`` — Outbox پایدار با Retry + Backoff + Dead-letter.

از زیرساختِ موجودِ صف دوباره‌استفاده می‌کند: همان الگویِ claim اتمیک (``select_for_update(skip_locked)`` + بازپس‌گیریِ claimِ کهنه)، همان ``BACKOFF_MINUTES`` و ``sanitize_error``.
قراردادِ هر کانال (``Channel``): ``enabled()`` · ``send(delivery, transport)`` → ``Outcome``. افزودنِ کانالِ جدید (SMS مدیر، موبایل…) فقط یک کلاس است.

هر بار پیش از ارسال دوباره بررسی می‌شود: کاربر هنوز فعال و دارایِ دسترسی است؟ اعلان هنوز خوانده/بایگانی‌نشده؟ کانال هنوز روشن است؟ (لغوِ دسترسی ⇒ هیچ ارسالی)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.notifications.models import NotificationDelivery, NotificationPreference
from apps.notifications.services import scope as S
from apps.notifications.services.notification_service import BACKOFF_MINUTES, STALE_CLAIM_MINUTES, sanitize_error

logger = logging.getLogger(__name__)
D = NotificationDelivery
Status, Chan = D.Status, D.Channel

MAX_PUSH_PER_10_MIN = 5
#: اعلانِ «به‌تعویق‌افتاده» (Snooze) تا پایانِ تعویق ارسال نمی‌شود: اگر پایانِ تعویق تا این بازه باشد، تحویل به همان لحظه موکول می‌شود (بدونِ مصرفِ تلاش و بدونِ شکستِ دائمی)؛
#: تعویقِ طولانی‌تر ⇒ «ارسال‌نشده» (یادآوریِ کهنه‌ی چنددوزه‌ای Push نمی‌شود). پس از پایانِ تعویق همان بررسی‌های معمول (خوانده/بایگانی/دسترسی/ترجیح) دوباره اجرا می‌شود.
SNOOZE_DEFER_MAX = timedelta(hours=24)


@dataclass
class Outcome:
    kind: str                 # delivered | retry | permanent | skipped
    detail: str = ""
    provider_ref: str = ""


class Channel:
    name = ""
    flag = ""

    def enabled(self) -> bool:
        return bool(getattr(settings, self.flag, False))

    def preference_on(self, pref: NotificationPreference) -> bool:
        return True

    def send(self, delivery, *, transport=None) -> Outcome:  # pragma: no cover - interface
        raise NotImplementedError


class WebPushChannel(Channel):
    name, flag = Chan.WEB_PUSH, "RASTISI_NOTIF_WEBPUSH_ENABLED"

    def preference_on(self, pref):
        return pref.browser_enabled

    def send(self, delivery, *, transport=None) -> Outcome:
        from apps.notifications.services import webpush

        sub = delivery.subscription
        if sub is None or sub.revoked_at is not None:
            return Outcome("skipped", "subscription_gone")
        if not webpush.is_configured():
            return Outcome("skipped", "vapid_not_configured")
        recent = D.objects.filter(channel=Chan.WEB_PUSH, inbox_item__user_id=delivery.inbox_item.user_id, status=Status.DELIVERED,
                                  sent_at__gte=timezone.now() - timedelta(minutes=10)).count()
        if recent >= MAX_PUSH_PER_10_MIN:
            return Outcome("skipped", "rate_limited")
        result = webpush.send(sub, transport=transport)
        code = result.status
        if code is not None and 200 <= code < 300:
            return Outcome("delivered")
        if code in (404, 410):                                    # اشتراکِ منقضی/نامعتبر ⇒ پاک‌سازی
            sub.revoked_at = timezone.now()
            sub.last_error = f"http {code}"
            sub.save(update_fields=["revoked_at", "last_error"])
            return Outcome("skipped", "subscription_gone")
        if code in (400, 401, 403, 413):                          # کلید/درخواستِ نادرست — تلاشِ مجدد بی‌فایده است
            return Outcome("permanent", f"http {code}")
        return Outcome("retry", f"http {code}" if code else (result.error or "network"))


class EmailChannel(Channel):
    """قراردادِ ایمیل: فقط Interface + ارسال با Backendِ تنظیم‌شده (در تست Locmem). پیش‌فرض خاموش؛ SMTP/Provider در مأموریتِ بعد."""

    name, flag = Chan.EMAIL, "RASTISI_NOTIF_EMAIL_ENABLED"

    def preference_on(self, pref):
        return pref.email_enabled

    def send(self, delivery, *, transport=None) -> Outcome:
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string

        user, ev = delivery.inbox_item.user, delivery.inbox_item.event
        if not getattr(user, "email", ""):
            return Outcome("skipped", "no_email")
        store_name = ev.store.name if ev.store_id else "راستی‌سی"
        text = "\n".join(p for p in (ev.summary, ev.details) if p)
        html = render_to_string("notifications/email/base.html", {"store_name": store_name, "subject": ev.title, "paragraphs": [p for p in text.splitlines() if p.strip()], "primary_color": "#6D28D9"})
        message = EmailMultiAlternatives(ev.title, text or ev.title, settings.DEFAULT_FROM_EMAIL, [user.email])
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        return Outcome("delivered")


class MobilePushChannel(Channel):
    """جایگاهِ اعلانِ موبایل (FCM/APNs) — هنوز Providerی متصل نیست؛ هرگز چیزی نمی‌فرستد."""

    name, flag = Chan.MOBILE_PUSH, "RASTISI_NOTIF_MOBILE_ENABLED"

    def preference_on(self, pref):
        return pref.mobile_enabled

    def send(self, delivery, *, transport=None) -> Outcome:
        return Outcome("skipped", "no_provider_configured")


CHANNELS = {c.name: c for c in (WebPushChannel(), EmailChannel(), MobilePushChannel())}


def _claim_batch(limit: int, now) -> list[NotificationDelivery]:
    stale = now - timedelta(minutes=STALE_CLAIM_MINUTES)
    with transaction.atomic():
        qs = (D.objects.select_for_update(skip_locked=True)
              .filter(attempts__lt=F("max_attempts"))
              .filter(Q(status=Status.PENDING) | Q(status=Status.FAILED) | Q(status=Status.SENDING, claimed_at__lt=stale))
              .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).order_by("id"))
        rows = list(qs[:limit])
        if rows:
            D.objects.filter(pk__in=[r.pk for r in rows]).update(status=Status.SENDING, claimed_at=now)
    return rows


def _still_allowed(delivery, channel, now) -> str:
    """نامِ دلیلِ ارسال‌نشدن، یا «» اگر همه‌چیز هنوز مجاز است."""
    item = delivery.inbox_item
    user, ev = item.user, item.event
    if not user.is_active:
        return "user_inactive"
    if ev.type_key not in S.allowed_type_keys(user, ev.store):
        return "access_revoked"
    if item.archived_at is not None or item.read_at is not None:
        return "already_seen"
    if item.snoozed_until is not None and item.snoozed_until > now:
        return "snoozed"
    if not channel.enabled():
        return "channel_disabled"
    pref = NotificationPreference.objects.filter(user=user, scope_key=item.scope_key).first() or NotificationPreference(user=user, scope_key=item.scope_key)
    if not channel.preference_on(pref):
        return "preference_off"
    return ""


def _process(delivery: NotificationDelivery, now, transports: dict) -> str:
    channel = CHANNELS.get(delivery.channel)
    reason = "unknown_channel" if channel is None else _still_allowed(delivery, channel, now)
    if reason == "snoozed":
        until = delivery.inbox_item.snoozed_until
        if until - now <= SNOOZE_DEFER_MAX:
            delivery.status, delivery.next_attempt_at, delivery.claimed_at = Status.PENDING, until, None      # موکول به پایانِ تعویق؛ attempts دست‌نخورده
            delivery.save(update_fields=["status", "next_attempt_at", "claimed_at"])
            return "deferred"
        reason = "snoozed_beyond_window"
    if reason:
        delivery.status, delivery.skip_reason, delivery.claimed_at = Status.SKIPPED, reason, None
        delivery.save(update_fields=["status", "skip_reason", "claimed_at"])
        return "skipped"
    delivery.attempts += 1
    try:
        outcome = channel.send(delivery, transport=transports.get(delivery.channel))
    except Exception as exc:  # noqa: BLE001 — یک تحویلِ خراب نباید بقیه‌ی صف را متوقف کند
        outcome = Outcome("retry", sanitize_error(f"{type(exc).__name__}: {exc}"))
    delivery.claimed_at = None
    if outcome.kind == "delivered":
        delivery.status, delivery.sent_at, delivery.last_error, delivery.next_attempt_at = Status.DELIVERED, now, "", None
        delivery.provider_ref = outcome.provider_ref
    elif outcome.kind == "skipped":
        delivery.status, delivery.skip_reason = Status.SKIPPED, outcome.detail
        delivery.attempts = max(delivery.attempts - 1, 0)
    else:
        delivery.last_error = sanitize_error(outcome.detail)
        if outcome.kind == "permanent" or delivery.attempts >= delivery.max_attempts:
            delivery.status, delivery.next_attempt_at = Status.DEAD, None
        else:
            delivery.status = Status.FAILED
            delivery.next_attempt_at = now + timedelta(minutes=BACKOFF_MINUTES[min(delivery.attempts - 1, len(BACKOFF_MINUTES) - 1)])
    delivery.save(update_fields=["status", "attempts", "sent_at", "last_error", "next_attempt_at", "claimed_at", "skip_reason", "provider_ref"])
    return {"delivered": "delivered", "skipped": "skipped"}.get(outcome.kind, "failed")


def deliver_pending(*, limit: int = 200, now=None, transports: dict | None = None) -> dict:
    now = now or timezone.now()
    counts = {"delivered": 0, "failed": 0, "skipped": 0, "deferred": 0}
    for delivery in _claim_batch(limit, now):
        counts[_process(delivery, now, transports or {})] += 1
    counts["processed"] = sum(counts.values())
    return counts
