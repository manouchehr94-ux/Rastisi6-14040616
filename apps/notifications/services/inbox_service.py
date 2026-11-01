"""صندوقِ اعلان: خواندنِ لیست/شمارنده/خلاصه‌ی Polling، و عملیاتِ خوانده/خوانده‌نشده/بایگانی/Snooze/سنجاق — همه فقط روی اعلان‌هایی که کاربر **هم‌اکنون** حق دیدنشان را دارد."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone as dt_tz

from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.notifications import registry as R
from apps.notifications.models import InboxItem, NotificationPreference
from apps.notifications.services import scope as S

PAGE_SIZE = 20
SNOOZE_CHOICES = {"1h": timedelta(hours=1), "4h": timedelta(hours=4), "tomorrow": timedelta(hours=18), "week": timedelta(days=7)}
SEVERITY_LABELS = {1: "اطلاعاتی", 2: "معمولی", 3: "مهم", 4: "بحرانی"}
SEVERITY_TONES = {1: "info", 2: "normal", 3: "important", 4: "critical"}


def visible(user, store=None):
    """تمامِ اعلان‌هایِ این کاربر در این محدوده که الان مجاز به دیدنشان است (عضویتِ فعال + مجوزِ نوعِ رویداد؛ لغوِ دسترسی فوراً اثر می‌کند)."""
    keys = S.allowed_type_keys(user, store)
    if not keys:
        return InboxItem.objects.none()
    return InboxItem.objects.filter(user=user, scope_key=S.key_for(store), event__type_key__in=keys).select_related("event")


def _active(qs, now):
    return qs.filter(archived_at__isnull=True).filter(Q(snoozed_until__isnull=True) | Q(snoozed_until__lte=now))


def unread_count(user, store=None, now=None) -> int:
    now = now or timezone.now()
    return _active(visible(user, store), now).filter(read_at__isnull=True).count()


def get_item(user, store, public_id):
    """فقط اگر متعلق به همین کاربر و محدوده و مجاز باشد؛ در غیرِ این صورت None (شناسه‌ی اعلانِ دیگران حدس‌زدنی/خواندنی نیست)."""
    try:
        return visible(user, store).filter(public_id=public_id).first()
    except (ValueError, TypeError):
        return None


def serialize(item, now=None) -> dict:
    ev = item.event
    now = now or timezone.now()
    return {
        "id": str(item.public_id), "title": ev.title, "summary": ev.summary, "severity": ev.severity,
        "tone": SEVERITY_TONES.get(ev.severity, "normal"), "severity_label": SEVERITY_LABELS.get(ev.severity, ""),
        "category": ev.category, "category_label": R.category_label(ev.category), "count": ev.occurrence_count,
        "read": item.read_at is not None, "pinned": item.pinned, "archived": item.archived_at is not None,
        "created_ms": int(item.created_at.timestamp() * 1000), "has_link": bool(ev.link_name),
        "popup": item.popup,
    }


def summary(user, store=None, *, since_ms: int = 0, limit: int = 8, now=None) -> dict:
    """پاسخِ سبکِ Polling: شمارنده + آخرین اعلان‌ها + اعلان‌هایِ تازه‌ی مستحقِ Toast (فقط خوانده‌نشده‌هایِ ساخته‌شده پس از ``since_ms``)."""
    now = now or timezone.now()
    base = _active(visible(user, store), now)
    unread = base.filter(read_at__isnull=True)
    latest = list(base.order_by("-pinned", "-id")[:limit])
    since = datetime.fromtimestamp(max(since_ms, 0) / 1000, tz=dt_tz.utc) if since_ms else now - timedelta(minutes=5)
    fresh = list(unread.filter(popup=True, created_at__gt=since, created_at__gte=now - timedelta(minutes=30)).order_by("id")[:5])
    return {"unread": unread.count(), "items": [serialize(i, now) for i in latest], "toasts": [serialize(i, now) for i in fresh], "now_ms": math.ceil(now.timestamp() * 1000)}


def filtered(user, store=None, params=None, now=None):
    """فیلتر/جست‌وجو/مرتب‌سازیِ صفحه‌ی کامل. ``params``: dict-مانند (GET)."""
    params = params or {}
    now = now or timezone.now()
    qs = visible(user, store)
    view = params.get("view", "")
    if view == "archived":
        qs = qs.filter(archived_at__isnull=False)
    else:
        qs = _active(qs, now)
    if view == "snoozed":
        qs = visible(user, store).filter(snoozed_until__gt=now, archived_at__isnull=True)
    if view == "unread" or params.get("unread") in ("1", "true"):
        qs = qs.filter(read_at__isnull=True)
    if view == "pinned":
        qs = qs.filter(pinned=True)
    sev = params.get("severity", "")
    if sev.isdigit() and int(sev) in (1, 2, 3, 4):
        qs = qs.filter(event__severity__gte=int(sev)) if params.get("sev_mode") == "min" else qs.filter(event__severity=int(sev))
    cat = params.get("category", "")
    if cat in R.CATEGORIES:
        qs = qs.filter(event__category=cat)
    days = params.get("range", "")
    if days.isdigit() and int(days) in (1, 7, 30, 90):
        qs = qs.filter(created_at__gte=now - timedelta(days=int(days)))
    q = (params.get("q") or "").strip()[:80]
    if q:
        qs = qs.filter(Q(event__title__icontains=q) | Q(event__summary__icontains=q) | Q(event__details__icontains=q))
    return qs.order_by("id" if params.get("sort") == "oldest" else "-id")


def mark(item, action: str, *, now=None, snooze: str = "") -> bool:
    now = now or timezone.now()
    if action == "read":
        item.read_at = item.read_at or now
    elif action == "unread":
        item.read_at = None
    elif action == "archive":
        item.archived_at = now
        item.read_at = item.read_at or now
    elif action == "unarchive":
        item.archived_at = None
    elif action == "pin":
        item.pinned = True
    elif action == "unpin":
        item.pinned = False
    elif action == "snooze":
        delta = SNOOZE_CHOICES.get(snooze)
        if delta is None:
            return False
        item.snoozed_until = now + delta
    elif action == "unsnooze":
        item.snoozed_until = None
    else:
        return False
    item.save(update_fields=["read_at", "archived_at", "pinned", "snoozed_until"])
    return True


def mark_all_read(user, store=None, now=None) -> int:
    now = now or timezone.now()
    ids = list(_active(visible(user, store), now).filter(read_at__isnull=True).values_list("pk", flat=True))
    return InboxItem.objects.filter(pk__in=ids).update(read_at=now)


def resolve_link(event, namespace: str) -> str:
    """نشانیِ مقصد از نامِ مسیر (نه نشانیِ خام) — در صورتِ نبودن/نامعتبر بودن رشته‌ی خالی."""
    if not event.link_name:
        return ""
    try:
        return reverse(f"{namespace}:{event.link_name}", kwargs=event.link_kwargs or {})
    except NoReverseMatch:
        return ""


def get_preference(user, store=None) -> NotificationPreference:
    pref, _ = NotificationPreference.objects.get_or_create(user=user, scope_key=S.key_for(store))
    return pref
