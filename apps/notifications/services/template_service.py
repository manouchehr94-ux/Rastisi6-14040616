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


def get_template(store, event_key: str, channel: str) -> dict:
    """قالبِ مؤثر: ردیفِ Store اگر موجود باشد وگرنه پیش‌فرضِ رویداد."""
    event = ev.get_event(event_key)
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
    body = (body or "").strip()
    subject = (subject or "").strip()
    if enabled and not body:
        raise TemplateError("متنِ قالبِ فعال نمی‌تواند خالی باشد.")
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


def reset_template(store, event_key: str, channel: str) -> None:
    NotificationTemplate.objects.filter(store=store, event_key=event_key, channel=channel).delete()


def preview(store, event_key: str, channel: str, *, subject: str | None = None, body: str | None = None) -> dict:
    """پیش‌نمایش با داده‌ی نمونه‌ی رویداد (بدونِ ذخیره و بدونِ ارسال)."""
    event = ev.get_event(event_key)
    current = get_template(store, event_key, channel)
    body = current["body"] if body is None else body
    subject = current["subject"] if subject is None else subject
    validate_text(event_key, body, what="متن")
    context = dict(event.sample)
    context["store_name"] = getattr(store, "name", context.get("store_name", ""))
    text, _ = render_text(body, context)
    result = {"body": text, "subject": "", "length": len(text), "sms_long": channel == ev.SMS and len(text) > SMS_SOFT_LIMIT}
    if channel == ev.EMAIL:
        validate_text(event_key, subject, what="موضوع")
        result["subject"] = render_text(subject, context)[0]
    return result
