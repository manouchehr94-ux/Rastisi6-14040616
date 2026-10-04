"""اعتبارسنجی، رندر و پیش‌نمایشِ قالب‌هایِ اعلان.

سینتکس: ``{متغیر}``؛ فقط متغیرهایِ مجازِ همان رویداد (``events.EVENTS``).
رندر با جایگزینیِ regex انجام می‌شود، نه ``str.format`` — پس هیچ دسترسیِ
ویژگی/ایندکس (``{x.__class__}``) ممکن نیست و هر آکولادِ ناشناخته خطاست."""

from __future__ import annotations

import re
from html import escape

from apps.notifications import events as ev
from apps.notifications.models import NotificationTemplate

_VAR_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
SMS_SOFT_LIMIT = 335  # ~۵ بخش پیامک فارسی؛ فقط هشدار، نه خطا


class TemplateError(ValueError):
    """قالبِ نامعتبر — پیام برایِ نمایش به مدیر مناسب است."""


def validate_text(event_key: str, text: str, *, what: str = "قالب") -> None:
    event = ev.get_event(event_key)
    allowed = set(event.variables)
    unknown = sorted({m for m in _VAR_RE.findall(text or "") if m not in allowed})
    if unknown:
        raise TemplateError(
            f"متغیرِ ناشناخته در {what}: " + "، ".join("{" + u + "}" for u in unknown)
            + ". متغیرهای مجاز: " + "، ".join("{" + a + "}" for a in sorted(allowed))
        )
    stripped = _VAR_RE.sub("", text or "")
    if "{" in stripped or "}" in stripped:
        raise TemplateError(f"آکولادِ نامعتبر در {what}؛ فقط برای متغیرها مجاز است.")


def render_text(text: str, context: dict, *, html: bool = False) -> tuple[str, list[str]]:
    """متن را رندر می‌کند → ``(متن، متغیرهایِ حل‌نشده)``. مقدارِ ``None``/غایب
    «حل‌نشده» است (رشته‌ی خالی معتبر است)."""
    missing: list[str] = []

    def sub(match):
        name = match.group(1)
        value = context.get(name)
        if value is None:
            missing.append(name)
            return ""
        value = str(value)
        return escape(value) if html else value

    return _VAR_RE.sub(sub, text or ""), missing


def is_legacy_sms(event_key: str, channel: str) -> bool:
    """پیامکِ این رویداد از قالبِ سراسریِ ``SmsTemplate`` (apps.sms) ارسال می‌شود."""
    return channel == ev.SMS and bool(ev.get_event(event_key).legacy_sms_event)


def is_platform_sms(event_key: str, channel: str) -> bool:
    """متنِ پیامکِ این رویداد فقط در اختیارِ پلتفرم است (کمپین/مناسبت): از ردیفِ سراسریِ
    ``SmsTemplate`` خوانده می‌شود و هیچ مسیرِ فروشگاه‌محوری حقِ نوشتن/جایگزینیِ آن را ندارد."""
    return channel == ev.SMS and bool(ev.get_event(event_key).platform_sms_event)


def _sms_source_event(event_key: str) -> str:
    event = ev.get_event(event_key)
    return event.legacy_sms_event or event.platform_sms_event


def _reads_from_sms_template(event_key: str, channel: str) -> bool:
    return is_legacy_sms(event_key, channel) or is_platform_sms(event_key, channel)


class PlatformManagedError(TemplateError):
    """تلاش برایِ ویرایشِ متنی که فقط پلتفرم مدیریت می‌کند."""


def _legacy_sms_row(event_key: str):
    from apps.sms.models import SmsTemplate

    SmsTemplate.ensure_defaults()
    return SmsTemplate.objects.filter(event_key=_sms_source_event(event_key)).first()


def get_template(store, event_key: str, channel: str) -> dict:
    """قالبِ مؤثر: برایِ پیامکِ رویدادهایِ قدیمی، ``SmsTemplate`` (همان که واقعاً ارسال
    می‌شود، با واژگانِ جدید)؛ وگرنه ردیفِ Store اگر موجود باشد وگرنه پیش‌فرضِ رویداد."""
    event = ev.get_event(event_key)
    if _reads_from_sms_template(event_key, channel):
        from apps.notifications import legacy_sms
        from apps.sms.events import DEFAULT_TEMPLATES

        source = _sms_source_event(event_key)
        row = _legacy_sms_row(event_key)
        body = row.body if row else DEFAULT_TEMPLATES.get(source, "")
        default = DEFAULT_TEMPLATES.get(source, "")
        return {
            "enabled": row.is_active if row else True, "subject": "", "extra_recipients": "",
            "body": legacy_sms.body_to_new(source, body),
            "customized": body != default, "row": None,
            "managed_by": "platform" if event.platform_sms_event else "legacy_sms",
        }
    row = NotificationTemplate.objects.filter(store=store, event_key=event_key, channel=channel).first()
    if row is not None:
        return {
            "enabled": row.is_enabled, "subject": row.subject, "body": row.body,
            "extra_recipients": row.extra_recipients, "customized": True, "row": row,
        }
    if channel == ev.SMS:
        return {
            "enabled": event.sms_enabled_default, "subject": "", "body": event.default_sms,
            "extra_recipients": "", "customized": False, "row": None,
        }
    return {
        "enabled": event.email_enabled_default, "subject": event.default_email_subject,
        "body": event.default_email_body, "extra_recipients": "", "customized": False, "row": None,
    }


def save_template(store, event_key: str, channel: str, *, enabled: bool, subject: str, body: str,
                  extra_recipients: str = "") -> NotificationTemplate:
    event = ev.get_event(event_key)
    if channel not in ev.CHANNELS:
        raise TemplateError("کانالِ نامعتبر.")
    if is_platform_sms(event_key, channel):
        raise PlatformManagedError("متنِ این پیامک را فقط راستی‌سی مدیریت می‌کند و قابلِ ویرایش نیست.")
    body = (body or "").strip()
    subject = (subject or "").strip()
    if enabled and not body:
        raise TemplateError("متنِ قالبِ فعال نمی‌تواند خالی باشد.")
    if is_legacy_sms(event_key, channel):
        return _save_legacy_sms(store, event_key, enabled=enabled, body=body)
    validate_text(event_key, body, what="متن")
    if channel == ev.EMAIL:
        if enabled and not subject:
            raise TemplateError("موضوعِ ایمیلِ فعال نمی‌تواند خالی باشد.")
        validate_text(event_key, subject, what="موضوع")
    else:
        subject = ""
    if event.audience != ev.AUDIENCE_STAFF:
        extra_recipients = ""
    row, _ = NotificationTemplate.objects.update_or_create(
        store=store, event_key=event_key, channel=channel,
        defaults={"is_enabled": enabled, "subject": subject, "body": body, "extra_recipients": extra_recipients.strip()},
    )
    return row


def _legacy_body_or_error(event_key: str, body: str) -> str:
    """متنِ ویرایشگر (واژگانِ جدید) → متنِ معتبرِ ``SmsTemplate`` یا ``TemplateError``."""
    from apps.notifications import legacy_sms
    from apps.sms.services.sms_service import SmsTemplateError, validate_template_body

    legacy_event = _sms_source_event(event_key)
    try:
        legacy_body = legacy_sms.body_to_legacy(legacy_event, body)
        validate_template_body(legacy_event, legacy_body)
    except (legacy_sms.LegacyTemplateError, SmsTemplateError) as exc:
        raise TemplateError(str(exc)) from exc
    return legacy_body


def _save_legacy_sms(store, event_key: str, *, enabled: bool, body: str) -> NotificationTemplate | None:
    """ذخیره در ``SmsTemplate`` (منبعِ حقیقتِ ارسال). ردیفِ بی‌اثرِ قدیمیِ
    ``NotificationTemplate`` برایِ همین رویداد/کانال حذف می‌شود تا نسخه‌ی دومِ
    پنهانی نماند. توجه: ``SmsTemplate`` سراسری است (مشترک میانِ فروشگاه‌ها)."""
    row = _legacy_sms_row(event_key)
    if body:  # متنِ خالیِ غیرفعال: متنِ فعلی دست‌نخورده می‌ماند، فقط وضعیت تغییر می‌کند
        row.body = _legacy_body_or_error(event_key, body)
    row.is_active = enabled
    row.save(update_fields=["body", "is_active", "updated_at"])
    NotificationTemplate.objects.filter(store=store, event_key=event_key, channel=ev.SMS).delete()
    return None


def reset_template(store, event_key: str, channel: str) -> None:
    if is_platform_sms(event_key, channel):
        raise PlatformManagedError("متنِ این پیامک را فقط راستی‌سی مدیریت می‌کند و قابلِ بازنشانی نیست.")
    if is_legacy_sms(event_key, channel):
        from apps.sms.events import DEFAULT_TEMPLATES

        row = _legacy_sms_row(event_key)
        row.body = DEFAULT_TEMPLATES[row.event_key]
        row.save(update_fields=["body", "updated_at"])
    NotificationTemplate.objects.filter(store=store, event_key=event_key, channel=channel).delete()


def preview(store, event_key: str, channel: str, *, subject: str | None = None, body: str | None = None) -> dict:
    """پیش‌نمایش با داده‌ی نمونه‌ی رویداد (بدونِ ذخیره و بدونِ ارسال)."""
    event = ev.get_event(event_key)
    current = get_template(store, event_key, channel)
    if is_platform_sms(event_key, channel):
        body = None  # متنِ پیامکِ پلتفرم‌محور هرگز از ورودیِ کاربر خوانده نمی‌شود
    body = current["body"] if body is None else body
    subject = current["subject"] if subject is None else subject
    if _reads_from_sms_template(event_key, channel):
        _legacy_body_or_error(event_key, body)
    else:
        validate_text(event_key, body, what="متن")
    context = dict(event.sample)
    context["store_name"] = getattr(store, "name", context.get("store_name", ""))
    if _reads_from_sms_template(event_key, channel):
        # `{{`/`}}` در متنِ قدیمی آکولادِ تحت‌اللفظی است
        from apps.notifications import legacy_sms
        from apps.sms.services import template_renderer

        legacy_event = _sms_source_event(event_key)
        text = template_renderer.render(
            legacy_sms.body_to_legacy(legacy_event, body),
            {old: context.get(new, "") for old, new in legacy_sms.legacy_to_new_map(legacy_event).items()},
            legacy_sms.legacy_to_new_map(legacy_event),
        )
    else:
        text, _ = render_text(body, context)
    result = {"body": text, "subject": "", "length": len(text), "sms_long": channel == ev.SMS and len(text) > SMS_SOFT_LIMIT}
    if channel == ev.EMAIL:
        validate_text(event_key, subject, what="موضوع")
        result["subject"] = render_text(subject, context)[0]
    return result
