"""توزیع‌کننده‌ی اعلانِ رویدادمحور (Transactional Outbox).

``dispatch_event`` هرگز چیزی نمی‌فرستد؛ برای هر کانالِ فعال و هر گیرنده یک
ردیفِ ``NotificationOutbox`` می‌سازد — همان تراکنشِ کسب‌وکار (سفارش/پرداخت…)
که فراخوان در آن است، پس اگر آن تراکنش rollback شود اعلان هم ساخته نمی‌شود و
اگر commit شود اعلان گم نمی‌شود. ارسالِ واقعی را ``deliver_pending``
(کارگرِ پس‌زمینه) با retry/backoff انجام می‌دهد؛ پس checkout/پرداخت هرگز منتظرِ
پیامک/ایمیل نمی‌ماند.

قوانین:

* رویدادِ ``PROMOTIONAL`` فقط با رضایتِ مشتری برایِ همان کانال ارسال می‌شود؛
  نبودِ رضایت یک ردیفِ ``SKIPPED`` (قابلِ ممیزی) می‌سازد، نه ارسال.
* ``dedupe_key`` (اختیاری) از ساختِ دوبارِ همان اعلان برایِ همان
  رویداد/کانال/گیرنده جلوگیری می‌کند (idempotency اجراهایِ تکراریِ job).
* گیرنده‌ی نامعتبر یا متغیرِ حل‌نشده ⇒ ``SKIPPED`` با دلیل؛ هرگز پیامِ
  نیمه‌رندرشده ارسال نمی‌شود.
* رویدادهایِ دارایِ ``legacy_sms_event`` پیامکشان را مسیرِ قدیمیِ ``apps.sms``
  می‌فرستد؛ این‌جا فقط ایمیل ساخته می‌شود (مگر ارسالِ آزمایشی).
"""

from __future__ import annotations

import hashlib
import logging
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone
from apps.notifications import events as ev
from apps.notifications.models import NotificationOutbox
from apps.notifications.services import template_service

logger = logging.getLogger(__name__)
S = NotificationOutbox.Status
_PHONE_LIKE = re.compile(r"^[\d+\-()\s۰-۹٠-٩]+$")


def _full_dedupe(store, event_key, dedupe_key, channel, recipient) -> str:
    if not dedupe_key:
        return ""
    raw = f"{store.pk}:{event_key}:{dedupe_key}:{channel}:{recipient}"
    return raw if len(raw) <= 200 else "h:" + hashlib.sha256(raw.encode()).hexdigest()


def _clean_recipient(channel: str, value: str):
    value = (value or "").strip()
    if not value:
        return None, ""
    if channel == ev.SMS:
        try:
            return normalize_iranian_phone(value), ""
        except InvalidPhoneError:
            return None, "invalid_recipient"
    try:
        validate_email(value)
    except ValidationError:
        return None, "invalid_recipient"
    return value, ""


def _staff_recipients(store, channel: str, extra: str) -> list[str]:
    values = [line.strip() for line in (extra or "").replace(",", "\n").splitlines() if line.strip()]
    # هر خط فقط به کانالِ مربوطه می‌رود: شماره → پیامک، هر چیزِ دیگر → ایمیل
    looks_phone = [bool(_PHONE_LIKE.match(v)) for v in values]
    values = [v for v, is_phone in zip(values, looks_phone) if is_phone == (channel == ev.SMS)]
    if channel == ev.EMAIL:
        from apps.stores.models import StoreMembership

        owners = StoreMembership.objects.filter(
            store=store, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        ).select_related("user")
        values += [m.user.email for m in owners if m.user.email]
    seen, unique = set(), []
    for v in values:
        if v.lower() not in seen:
            seen.add(v.lower())
            unique.append(v)
    return unique


def _customer_recipient(customer, channel: str) -> str:
    if customer is None:
        return ""
    return customer.phone if channel == ev.SMS else customer.email


def _consented(customer, channel: str) -> bool:
    if customer is None:
        return False
    return customer.accepts_promotional_sms if channel == ev.SMS else customer.accepts_promotional_email


def _create(*, store, event, channel, recipient, subject, body, customer, order, dedupe, is_promotional,
            status=S.PENDING, skip_reason="", is_test=False, metadata=None):
    data = dict(
        channel=channel, store=store, subject=subject, body=body, event_key=event.key, customer=customer,
        order=order, is_promotional=is_promotional, is_security=(event.category == ev.SECURITY),
        dedupe_key=dedupe, status=status, skip_reason=skip_reason, is_test=is_test, metadata=metadata or {},
        recipient_phone=recipient if channel == ev.SMS else "",
        recipient_email=recipient if channel == ev.EMAIL else "",
        recipient_user=getattr(customer, "user", None) if customer is not None else None,
    )
    try:
        with transaction.atomic():
            return NotificationOutbox.objects.create(**data), True
    except IntegrityError:
        if dedupe:
            return NotificationOutbox.objects.filter(dedupe_key=dedupe).first(), False
        raise


def dispatch_event(
    event_key: str, *, store, customer=None, order=None, context: dict | None = None,
    dedupe_key: str = "", channels=None, is_test: bool = False, test_recipient: str | None = None,
    overrides: dict | None = None, metadata: dict | None = None,
) -> list[NotificationOutbox]:
    """``overrides``: ``{"sms": {"body": ...}, "email": {"subject": ..., "body": ...}}`` —
    متنِ اختصاصیِ یک کمپین (قبلاً با ``validate_text`` اعتبارسنجی شده)؛ وجودِ
    override یعنی آن کانال برایِ این ارسال فعال است. ``metadata``: به
    ``NotificationOutbox.metadata`` اضافه می‌شود (مثلاً شناسه‌ی صدور)."""
    event = ev.get_event(event_key)
    context = dict(context or {})
    context.setdefault("store_name", store.name)
    created: list[NotificationOutbox] = []
    promotional = event.category == ev.PROMOTIONAL

    for channel in channels or ev.CHANNELS:
        if channel == ev.SMS and event.legacy_sms_event and not is_test:
            continue
        tpl = dict(template_service.get_template(store, event_key, channel))
        override = (overrides or {}).get(channel) or {}
        if override.get("body"):
            tpl["body"] = override["body"]
            if channel == ev.EMAIL and override.get("subject"):
                tpl["subject"] = override["subject"]
            tpl["enabled"] = True
        if not tpl["enabled"] and not is_test:
            continue

        if is_test:
            recipients = [test_recipient] if test_recipient else []
        elif event.audience == ev.AUDIENCE_STAFF:
            recipients = _staff_recipients(store, channel, tpl["extra_recipients"])
        else:
            recipients = [_customer_recipient(customer, channel)]

        subject, missing_s = template_service.render_text(tpl["subject"], context)
        body, missing_b = template_service.render_text(tpl["body"], context)
        missing = sorted(set(missing_s + missing_b))

        for raw in recipients:
            recipient, bad = _clean_recipient(channel, raw)
            if recipient is None and not bad:
                continue  # گیرنده‌ی خالی — برایِ این کانال چیزی ثبت نمی‌شود
            dedupe = _full_dedupe(store, event_key, dedupe_key, channel, recipient or raw)
            common = dict(
                store=store, event=event, channel=channel, recipient=recipient or (raw or "")[:120],
                subject=subject, body=body, customer=customer, order=order, dedupe=dedupe,
                is_promotional=promotional, is_test=is_test, metadata=metadata,
            )
            if bad:
                row, new = _create(**common, status=S.SKIPPED, skip_reason=bad)
            elif missing:
                row, new = _create(**common, status=S.SKIPPED, skip_reason="unresolved_variables:" + ",".join(missing))
                logger.warning("notification %s skipped: unresolved variables %s", event_key, missing)
            elif promotional and not is_test and event.audience == ev.AUDIENCE_CUSTOMER and not _consented(customer, channel):
                row, new = _create(**common, status=S.SKIPPED, skip_reason="no_promotional_consent")
            else:
                row, new = _create(**common)
            if new:
                created.append(row)
    return created


def safe_dispatch(event_key: str, **kwargs) -> list[NotificationOutbox]:
    """مثلِ ``dispatch_event`` اما هرگز استثنا پرتاب نمی‌کند و تراکنشِ بیرونی
    را خراب نمی‌کند (savepoint) — اعلان نباید checkout/پرداخت را بشکند."""
    try:
        with transaction.atomic():
            return dispatch_event(event_key, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("notification dispatch failed for event %s", event_key)
        return []
