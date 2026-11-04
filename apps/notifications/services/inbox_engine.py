"""موتورِ مرکزیِ اعلانِ مدیران: ``publish`` ← رجیستری ← Policy ← گیرندگان ← InboxItem + NotificationDelivery.

* همه‌چیز **در تراکنشِ فراخوان** (Transactional Outbox): rollback ⇒ نه رویداد، نه صندوق، نه ردیفِ تحویل. ارسالِ بیرونی را فقط کارگر (``channel_delivery``) پس از commit انجام می‌دهد؛ پس خرابیِ کانال هرگز Checkout/عملیاتِ اصلی را نمی‌شکند.
* Dedupe: ``(scope_key, dedupe_key)`` یکتا ⇒ اجرای دوبارِ همان Trigger اعلانِ دوم نمی‌سازد. رویدادهای ``groupable`` شمارنده را زیاد می‌کنند (یک ردیف به‌جای سیل).
* ``safe_publish`` هرگز استثنا پرتاب نمی‌کند (savepoint)."""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.notifications import registry as R
from apps.notifications.models import InboxItem, NotificationDelivery, NotificationEvent, NotificationPreference, WebPushSubscription
from apps.notifications.services import scope as S
from apps.notifications.services.notification_service import sanitize_error

logger = logging.getLogger(__name__)

PLATFORM_URLCONF = "shop_core.urls_platform_admin"
GROUP_WINDOW = timedelta(hours=24)
MAX_EVENTS_PER_HOUR = 300           # سقفِ ایمنی برایِ هر (نوع × محدوده): سیلِ رویداد صندوق را پر نمی‌کند
MAX_PUSH_PER_10_MIN = 5             # سقفِ Push برایِ هر کاربر

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LONG_SECRET = re.compile(r"\b(?:[A-Za-z0-9_\-]{32,}|(?:sk|pk|tok|key|secret)[_\-][A-Za-z0-9_\-]{8,})\b")


def safe_text(value, limit: int) -> str:
    """متنِ امن برایِ نمایش: بدونِ کاراکترِ کنترلی، موبایل/ایمیل ماسک، رشته‌های شبیهِ توکن حذف، طول محدود. (نمایش همیشه escape می‌شود.)"""
    text = sanitize_error(_CONTROL.sub("", str(value or "")))
    text = _LONG_SECRET.sub("***", text)
    return text.strip()[:limit]


def default_preference(user, scope_key: str) -> NotificationPreference:
    return NotificationPreference(user=user, scope_key=scope_key)


def preferences_for(users, scope_key: str) -> dict:
    found = {p.user_id: p for p in NotificationPreference.objects.filter(user__in=users, scope_key=scope_key)}
    return {u.pk: found.get(u.pk) or default_preference(u, scope_key) for u in users}


def decide(etype: R.EventType, severity: int, pref: NotificationPreference, force_inbox: bool = False) -> dict:
    """Policy: چه چیزی برایِ این گیرنده ساخته/نمایش داده شود.
    * صندوق: دسته خاموش نباشد — مگر امنیتی/بحرانی (همیشه ثبت می‌شود).
    * Toast: صندوق + toast روشن + (اهمیت ≥ حداقل یا رویدادِ فوری)؛ «بی‌صداکردنِ کم‌اهمیت» اطلاعاتی/معمولیِ غیرفوری را حذف می‌کند.
    * مرورگر: صندوق + browser روشن + اهمیت ≥ حداقل (یا فوری)."""
    disabled = set(pref.disabled_categories or [])
    inbox = force_inbox or (etype.category not in disabled) or severity >= R.CRITICAL or etype.category in R.ALWAYS_INBOX_CATEGORIES
    low = severity < R.IMPORTANT and not etype.urgent
    muted = pref.mute_low and low
    toast = inbox and pref.toast_enabled and not muted and (severity >= pref.min_toast_severity or etype.urgent)
    push = inbox and pref.browser_enabled and not muted and (severity >= pref.min_browser_severity or etype.urgent)
    return {"inbox": inbox, "toast": bool(toast), "push": bool(push), "email": inbox and pref.email_enabled, "mobile": inbox and pref.mobile_enabled}


def _link_ok(etype: R.EventType, link_kwargs: dict) -> bool:
    if not etype.link_name:
        return True
    ns = "portal_platform_admin" if etype.scope == R.PLATFORM else "dashboard"
    urlconf = PLATFORM_URLCONF if etype.scope == R.PLATFORM else None     # مسیرهای پلتفرم فقط در urlconfِ همان هاست ثبت‌اند؛ publish ممکن است از هاستِ دیگر/Cron بیاید
    try:
        reverse(f"{ns}:{etype.link_name}", kwargs=link_kwargs or {}, urlconf=urlconf)
        return True
    except NoReverseMatch:
        return False


def _recent_count(type_key: str, scope_key: str, now) -> int:
    return NotificationEvent.objects.filter(type_key=type_key, scope_key=scope_key, created_at__gte=now - timedelta(hours=1)).count()


def publish(
    type_key: str, *, store=None, title: str = "", summary: str = "", details: str = "", entity: tuple | None = None, link_kwargs: dict | None = None,
    dedupe_key: str = "", group_key: str = "", occurred_at=None, metadata: dict | None = None, severity: int | None = None,
    only_users=None, force_inbox=None,
) -> NotificationEvent | None:
    """رویدادِ واقعی را به اعلانِ پایدار تبدیل می‌کند. ``only_users``: محدودکردنِ گیرندگان (مثلاً اعلانِ آزمایشی فقط برایِ خودِ کاربر)."""
    etype = R.get_type(type_key)
    if etype.scope == R.STORE and store is None:
        raise ValueError(f"{type_key} needs a store")
    if etype.scope == R.PLATFORM and store is not None:
        raise ValueError(f"{type_key} is platform-scoped")
    now = timezone.now()
    scope_key = S.key_for(store)
    link_kwargs = dict(link_kwargs or {})
    sev = int(severity or etype.severity)

    if dedupe_key and NotificationEvent.objects.filter(scope_key=scope_key, dedupe_key=dedupe_key).exists():
        return None                                                    # همین رویداد قبلاً اعلان شده
    if _recent_count(type_key, scope_key, now) >= MAX_EVENTS_PER_HOUR:
        logger.warning("notification flood guard: %s @ %s dropped", type_key, scope_key)
        return None

    if etype.groupable and group_key:                                  # تجمیع: همان گروه در ۲۴ ساعتِ اخیر ⇒ فقط شمارنده
        existing = NotificationEvent.objects.filter(scope_key=scope_key, type_key=type_key, group_key=group_key, updated_at__gte=now - GROUP_WINDOW).first()
        if existing is not None:
            NotificationEvent.objects.filter(pk=existing.pk).update(occurrence_count=existing.occurrence_count + 1, updated_at=now,
                                                                   summary=safe_text(summary, 300) or existing.summary)
            InboxItem.objects.filter(event=existing, archived_at__isnull=True).update(read_at=None)
            return existing

    event_kwargs = dict(
        type_key=type_key, category=etype.category, severity=sev, scope=etype.scope, scope_key=scope_key, store=store,
        title=safe_text(title or etype.label, 160), summary=safe_text(summary, 300), details=safe_text(details, 2000),
        entity_type=(entity[0] if entity else "")[:40], entity_id=str(entity[1] if entity else "")[:40],
        link_name=etype.link_name if _link_ok(etype, link_kwargs) else "", link_kwargs=link_kwargs,
        link_permission=etype.permission, required_permission=etype.permission,
        occurred_at=occurred_at or now, dedupe_key=dedupe_key[:200], group_key=group_key[:200],
        expires_at=now + timedelta(days=etype.retention_days), metadata={k: safe_text(v, 120) if isinstance(v, str) else v for k, v in (metadata or {}).items()},
    )
    try:
        with transaction.atomic():
            event = NotificationEvent.objects.create(**event_kwargs)
    except IntegrityError:
        return None                                                    # مسابقه‌ی همزمان روی dedupe

    recipients = S.platform_recipients() if etype.scope == R.PLATFORM else S.store_recipients(store, etype.permission)
    recipients = [u for u in recipients if only_users is None or u.pk in {x.pk for x in only_users}]
    prefs = preferences_for(recipients, scope_key)
    items, plans = [], []
    for user in recipients:
        forced = force_inbox is not None and user.pk in {x.pk for x in force_inbox}      # اعلانِ آزمایشیِ خودِ کاربر همیشه دیده می‌شود (حتی اگر دسته را خاموش کرده)
        d = decide(etype, sev, prefs[user.pk], force_inbox=forced)
        if not d["inbox"]:
            continue
        items.append(InboxItem(event=event, user=user, scope_key=scope_key, popup=d["toast"]))
        plans.append((user, d))
    InboxItem.objects.bulk_create(items)
    saved = {i.user_id: i for i in InboxItem.objects.filter(event=event)}
    _create_deliveries(event, etype, scope_key, [(saved[u.pk], d) for u, d in plans if u.pk in saved], now)
    return event


def _create_deliveries(event, etype, scope_key, planned, now) -> None:
    rows = []
    if getattr(settings, "RASTISI_NOTIF_WEBPUSH_ENABLED", False):
        from apps.notifications.services import webpush

        if webpush.is_configured():
            for item, d in planned:
                if not d["push"]:
                    continue
                for sub in WebPushSubscription.objects.filter(user_id=item.user_id, scope_key=scope_key, revoked_at__isnull=True):
                    rows.append(NotificationDelivery(inbox_item=item, channel=NotificationDelivery.Channel.WEB_PUSH, target_key=f"sub:{sub.pk}", subscription=sub))
    if getattr(settings, "RASTISI_NOTIF_EMAIL_ENABLED", False):
        for item, d in planned:
            if d["email"] and getattr(item.user, "email", ""):
                rows.append(NotificationDelivery(inbox_item=item, channel=NotificationDelivery.Channel.EMAIL, target_key="email"))
    if getattr(settings, "RASTISI_NOTIF_MOBILE_ENABLED", False):
        for item, d in planned:
            if d["mobile"]:
                rows.append(NotificationDelivery(inbox_item=item, channel=NotificationDelivery.Channel.MOBILE_PUSH, target_key="mobile"))
    if rows:
        NotificationDelivery.objects.bulk_create(rows, ignore_conflicts=True)


def safe_publish(type_key: str, **kwargs) -> NotificationEvent | None:
    """هرگز استثنا پرتاب نمی‌کند و تراکنشِ بیرونی را خراب نمی‌کند (savepoint) — اعلان نباید Checkout/پرداخت/ورودِ گروهی را بشکند."""
    try:
        with transaction.atomic():
            return publish(type_key, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("notification publish failed for %s", type_key)
        return None


def prune(now=None) -> dict:
    """سیاستِ نگهداری: رویدادهایِ منقضی (``expires_at``) به‌همراهِ سهمِ گیرندگان حذف می‌شوند؛ اعلانِ سنجاق‌شده تا حذفِ دستی می‌ماند."""
    now = now or timezone.now()
    pinned = InboxItem.objects.filter(pinned=True).values_list("event_id", flat=True)
    qs = NotificationEvent.objects.filter(expires_at__lt=now).exclude(pk__in=list(pinned))
    count = qs.count()
    qs.delete()
    return {"deleted_events": count}
