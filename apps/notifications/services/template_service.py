"""اعتبارسنجی، رندر و پیش‌نمایشِ قالب‌هایِ اعلان.

سینتکس: ``{متغیر}``؛ فقط متغیرهایِ مجازِ همان رویداد (``events.EVENTS``).
رندر با جایگزینیِ regex انجام می‌شود، نه ``str.format`` — پس هیچ دسترسیِ
ویژگی/ایندکس (``{x.__class__}``) ممکن نیست و هر آکولادِ ناشناخته خطاست."""

from __future__ import annotations

import re
from html import escape

from apps.notifications import events as ev
from apps.notifications.models import NotificationTemplate
from apps.notifications.services.html_sanitizer import sanitize_html

_VAR_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
SMS_SOFT_LIMIT = 335  # ~۵ بخش پیامک فارسی؛ فقط هشدار، نه خطا
MAX_HTML_LENGTH = 20_000


class TemplateError(ValueError):
    """قالبِ نامعتبر — پیام برایِ نمایش به مدیر مناسب است."""


def validate_text(event_key: str, text: str, *, what: str = "قالب", check_required: bool = False) -> None:
    event = ev.get_event(event_key)
    allowed = set(event.variables)
    present = set(_VAR_RE.findall(text or ""))
    unknown = sorted(present - allowed)
    if unknown:
        raise TemplateError(
            f"متغیرِ ناشناخته در {what}: " + "، ".join("{" + u + "}" for u in unknown)
            + ". متغیرهای مجاز: " + "، ".join("{" + a + "}" for a in sorted(allowed))
        )
    stripped = _VAR_RE.sub("", text or "")
    if "{" in stripped or "}" in stripped:
        raise TemplateError(f"آکولادِ نامعتبر در {what}؛ فقط برای متغیرها مجاز است.")
    missing_required = sorted(set(event.required_variables) - present)
    if check_required and text and missing_required:  # فقط متنِ اصلی؛ موضوع الزاماً همه‌ی متغیرها را ندارد
        raise TemplateError(
            f"متغیرِ ضروری در {what} حذف شده: " + "، ".join("{" + m + "}" for m in missing_required)
        )


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


def _platform_row(event_key: str, channel: str):
    from apps.notifications.models import PlatformNotificationTemplate

    return PlatformNotificationTemplate.objects.filter(event_key=event_key, channel=channel).first()


def is_store_locked(event_key: str, channel: str) -> bool:
    """فروشگاه حق بازنویسیِ این قالب را ندارد: اعلانِ پلتفرم به مدیرِ فروشگاه، یا قفلِ صریحِ پلتفرم."""
    if ev.get_event(event_key).sender == "platform":
        return True
    row = _platform_row(event_key, channel)
    return bool(row and row.locked_for_stores)


def get_template(store, event_key: str, channel: str) -> dict:
    """قالبِ مؤثر — وراثتِ قابل‌پیش‌بینی: **پیش‌فرضِ پلتفرم ← بازنویسیِ فروشگاه ← اعلانِ رندرشده**.

    برایِ پیامکِ رویدادهایِ قدیمی، ``SmsTemplate`` (همان که واقعاً ارسال می‌شود). وگرنه: ردیفِ Store
    (مگر قفل باشد) ← ردیفِ پیش‌فرضِ پلتفرم ← پیش‌فرضِ داخلِ کدِ رویداد. اعلان‌هایِ ``SECURITY`` همیشه فعال‌اند."""
    event = ev.get_event(event_key)
    if _reads_from_sms_template(event_key, channel):
        from apps.notifications import legacy_sms
        from apps.sms.events import DEFAULT_TEMPLATES

        source = _sms_source_event(event_key)
        row = _legacy_sms_row(event_key)
        body = row.body if row else DEFAULT_TEMPLATES.get(source, "")
        default = DEFAULT_TEMPLATES.get(source, "")
        return {
            "enabled": row.is_active if row else True, "subject": "", "extra_recipients": "", "body_html": "",
            "body": legacy_sms.body_to_new(source, body),
            "customized": body != default, "row": None, "source": "legacy_sms", "locked": False, "version": 0,
            "security_locked": False,
            "managed_by": "platform" if event.platform_sms_event else "legacy_sms",
        }
    platform = _platform_row(event_key, channel)
    locked = event.sender == "platform" or bool(platform and platform.locked_for_stores)
    row = None if (locked or store is None) else NotificationTemplate.objects.filter(
        store=store, event_key=event_key, channel=channel).first()
    if row is not None:
        data = {
            "enabled": row.is_enabled, "subject": row.subject, "body": row.body, "body_html": row.body_html,
            "extra_recipients": row.extra_recipients, "customized": True, "row": row, "source": "store",
            "version": row.version,
        }
    elif platform is not None:
        data = {
            "enabled": platform.is_enabled, "subject": platform.subject, "body": platform.body,
            "body_html": platform.body_html, "extra_recipients": "", "customized": False, "row": None,
            "source": "platform", "version": platform.version,
        }
    elif channel == ev.SMS:
        data = {
            "enabled": event.sms_enabled_default, "subject": "", "body": event.default_sms, "body_html": "",
            "extra_recipients": "", "customized": False, "row": None, "source": "default", "version": 0,
        }
    else:
        data = {
            "enabled": event.email_enabled_default, "subject": event.default_email_subject,
            "body": event.default_email_body, "body_html": "", "extra_recipients": "", "customized": False,
            "row": None, "source": "default", "version": 0,
        }
    data["locked"] = locked
    data["security_locked"] = event.category == ev.SECURITY
    if event.category == ev.SECURITY:
        data["enabled"] = True  # اعلانِ امنیتی را نه فروشگاه می‌تواند خاموش کند نه پلتفرم
    return data


# --------------------------------------------------------------------------------------------------- HTML
def clean_html_template(event_key: str, html: str) -> str:
    """HTMLِ قالب → نسخه‌ی پاک‌سازی‌شده (allowlist) + اعتبارسنجیِ متغیرها. هیچ عبارتِ پایتون/جینجا اجرا نمی‌شود."""
    html = (html or "").strip()
    if not html:
        return ""
    if len(html) > MAX_HTML_LENGTH:
        raise TemplateError("متنِ HTML بیش از حدِ مجاز (۲۰٬۰۰۰ نویسه) است.")
    cleaned = sanitize_html(html, allow_placeholders=True)
    if not cleaned:
        raise TemplateError("متنِ HTML پس از حذفِ برچسب‌هایِ غیرمجاز خالی شد.")
    validate_text(event_key, cleaned, what="HTML", check_required=True)
    return cleaned


def render_html(event_key: str, html_template: str, context: dict) -> tuple[str, list[str]]:
    """رندرِ HTML: مقادیرِ متغیرها escape می‌شوند و خروجی دوباره (سخت‌گیرانه) پاک‌سازی می‌شود — پیوندِ
    ``javascript:`` که از طریقِ یک مقدارِ متغیر وارد شود حذف می‌شود."""
    if not html_template:
        return "", []
    text, missing = render_text(html_template, context, html=True)
    return sanitize_html(text, allow_placeholders=False), missing


def render_email_document(store, subject: str, body: str, html_fragment: str = "") -> str:
    """مستندِ کاملِ ایمیل (قالبِ واکنش‌گرا + RTL + هویتِ برند). تنها جایی که ایمیلِ نهایی ساخته می‌شود —
    هم ارسالِ واقعی و هم پیش‌نمایش از همین استفاده می‌کنند."""
    from django.template.loader import render_to_string

    primary = "#6D28D9"
    name = getattr(store, "name", "") or "راستی‌سی"
    if store is not None and getattr(store, "pk", None):
        try:
            from apps.core.models import ShopSettings

            primary = ShopSettings.load(store=store).primary_color or primary
        except Exception:  # noqa: BLE001 — هویتِ بصری اختیاری است
            pass
    return render_to_string("notifications/email/base.html", {
        "store_name": name, "subject": subject, "primary_color": primary,
        "content_html": html_fragment,
        "paragraphs": [line for line in (body or "").splitlines() if line.strip()],
    })


# ------------------------------------------------------------------------------------------------ revisions
def _record_revision(*, scope: str, store, event_key: str, channel: str, version: int, action: str, enabled: bool,
                     subject: str, body: str, body_html: str, actor) -> None:
    from apps.notifications.models import NotificationTemplateRevision

    NotificationTemplateRevision.objects.create(
        scope=scope, store=store, event_key=event_key, channel=channel, version=version, action=action,
        is_enabled=enabled, subject=subject, body=body, body_html=body_html, actor=actor,
    )


def list_revisions(*, scope: str, store, event_key: str | None = None, channel: str | None = None, limit: int = 50):
    from apps.notifications.models import NotificationTemplateRevision

    qs = NotificationTemplateRevision.objects.filter(scope=scope, store=store).select_related("actor")
    if event_key:
        qs = qs.filter(event_key=event_key)
    if channel:
        qs = qs.filter(channel=channel)
    return list(qs[:limit])


def _check_body_rules(event, channel: str, *, enabled: bool, subject: str, body: str, body_html: str):
    if enabled and not body:
        raise TemplateError("متنِ قالبِ فعال نمی‌تواند خالی باشد.")
    validate_text(event.key, body, what="متن", check_required=True)
    if channel == ev.EMAIL:
        if enabled and not subject:
            raise TemplateError("موضوعِ ایمیلِ فعال نمی‌تواند خالی باشد.")
        validate_text(event.key, subject, what="موضوع")
        return clean_html_template(event.key, body_html)
    return ""


def save_template(store, event_key: str, channel: str, *, enabled: bool, subject: str, body: str,
                  extra_recipients: str = "", body_html: str = "", actor=None) -> NotificationTemplate:
    event = ev.get_event(event_key)
    if channel not in ev.CHANNELS:
        raise TemplateError("کانالِ نامعتبر.")
    if is_platform_sms(event_key, channel):
        raise PlatformManagedError("متنِ این پیامک را فقط راستی‌سی مدیریت می‌کند و قابلِ ویرایش نیست.")
    if is_store_locked(event_key, channel):
        raise PlatformManagedError("این قالب را فقط راستی‌سی مدیریت می‌کند و قابلِ ویرایش نیست.")
    body = (body or "").strip()
    subject = (subject or "").strip()
    if event.category == ev.SECURITY:
        enabled = True  # اعلانِ امنیتی غیرقابلِ‌غیرفعال‌سازی است (سیاستِ پلتفرم)
    if is_legacy_sms(event_key, channel):
        if enabled and not body:
            raise TemplateError("متنِ قالبِ فعال نمی‌تواند خالی باشد.")
        return _save_legacy_sms(store, event_key, enabled=enabled, body=body)
    html = _check_body_rules(event, channel, enabled=enabled, subject=subject, body=body, body_html=body_html)
    if channel == ev.SMS:
        subject = ""
    if event.audience != ev.AUDIENCE_STAFF:
        extra_recipients = ""
    row = NotificationTemplate.objects.filter(store=store, event_key=event_key, channel=channel).first()
    if row is None:
        row = NotificationTemplate(store=store, event_key=event_key, channel=channel, version=1)
    else:
        row.version += 1
    row.is_enabled, row.subject, row.body, row.body_html = enabled, subject, body, html
    row.extra_recipients = (extra_recipients or "").strip()
    row.save()
    _record_revision(scope="store", store=store, event_key=event_key, channel=channel, version=row.version,
                     action="save", enabled=enabled, subject=subject, body=body, body_html=html, actor=actor)
    return row


def set_channel_enabled(store, event_key: str, channel: str, enabled: bool, *, actor=None):
    """کلیدِ روشن/خاموشِ مستقلِ یک کانال برایِ یک رویدادِ فروشگاه — متنِ مؤثرِ فعلی را دست‌نخورده نگه می‌دارد."""
    event = ev.get_event(event_key)
    if event.category == ev.SECURITY and not enabled:
        raise TemplateError("اعلانِ امنیتی غیرقابلِ غیرفعال‌سازی است.")
    if _reads_from_sms_template(event_key, channel):
        raise PlatformManagedError("روشن/خاموشیِ این پیامک از بخشِ تنظیماتِ پیامک مدیریت می‌شود.")
    current = get_template(store, event_key, channel)
    return save_template(
        store, event_key, channel, enabled=enabled, subject=current["subject"], body=current["body"],
        body_html=current.get("body_html", ""), extra_recipients=current.get("extra_recipients", ""), actor=actor,
    )


# ------------------------------------------------------------------------------------- platform defaults
def save_platform_template(event_key: str, channel: str, *, enabled: bool, subject: str, body: str,
                           body_html: str = "", locked_for_stores: bool = False, actor=None):
    from apps.notifications.models import PlatformNotificationTemplate

    event = ev.get_event(event_key)
    if channel not in ev.CHANNELS:
        raise TemplateError("کانالِ نامعتبر.")
    if _reads_from_sms_template(event_key, channel):
        raise PlatformManagedError("متنِ این پیامک از بخشِ «قالب‌هایِ پیامک» پلتفرم مدیریت می‌شود.")
    body, subject = (body or "").strip(), (subject or "").strip()
    if event.category == ev.SECURITY:
        enabled = True
    html = _check_body_rules(event, channel, enabled=enabled, subject=subject, body=body, body_html=body_html)
    if channel == ev.SMS:
        subject = ""
    row = PlatformNotificationTemplate.objects.filter(event_key=event_key, channel=channel).first()
    if row is None:
        row = PlatformNotificationTemplate(event_key=event_key, channel=channel, version=1)
    else:
        row.version += 1
    row.is_enabled, row.subject, row.body, row.body_html = enabled, subject, body, html
    row.locked_for_stores = bool(locked_for_stores)
    row.updated_by = actor
    row.save()
    _record_revision(scope="platform", store=None, event_key=event_key, channel=channel, version=row.version,
                     action="save", enabled=enabled, subject=subject, body=body, body_html=html, actor=actor)
    return row


def reset_platform_template(event_key: str, channel: str, *, actor=None) -> None:
    from apps.notifications.models import PlatformNotificationTemplate

    row = PlatformNotificationTemplate.objects.filter(event_key=event_key, channel=channel).first()
    if row is None:
        return
    _record_revision(scope="platform", store=None, event_key=event_key, channel=channel, version=row.version + 1,
                     action="reset", enabled=row.is_enabled, subject=row.subject, body=row.body,
                     body_html=row.body_html, actor=actor)
    row.delete()


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


def reset_template(store, event_key: str, channel: str, *, actor=None) -> None:
    """بازگشت به پیش‌فرض: بازنویسیِ فروشگاه حذف می‌شود و قالبِ مؤثر دوباره «پیش‌فرضِ پلتفرم» است."""
    if is_platform_sms(event_key, channel):
        raise PlatformManagedError("متنِ این پیامک را فقط راستی‌سی مدیریت می‌کند و قابلِ بازنشانی نیست.")
    if is_legacy_sms(event_key, channel):
        from apps.sms.events import DEFAULT_TEMPLATES

        row = _legacy_sms_row(event_key)
        row.body = DEFAULT_TEMPLATES[row.event_key]
        row.save(update_fields=["body", "updated_at"])
    existing = NotificationTemplate.objects.filter(store=store, event_key=event_key, channel=channel).first()
    if existing is not None:
        _record_revision(scope="store", store=store, event_key=event_key, channel=channel, version=existing.version + 1,
                         action="reset", enabled=existing.is_enabled, subject=existing.subject, body=existing.body,
                         body_html=existing.body_html, actor=actor)
        existing.delete()


def preview(store, event_key: str, channel: str, *, subject: str | None = None, body: str | None = None,
            body_html: str | None = None) -> dict:
    """پیش‌نمایش با داده‌ی نمونه‌ی رویداد (بدونِ ذخیره و بدونِ ارسال)."""
    event = ev.get_event(event_key)
    current = get_template(store, event_key, channel)
    if is_platform_sms(event_key, channel):
        body = None  # متنِ پیامکِ پلتفرم‌محور هرگز از ورودیِ کاربر خوانده نمی‌شود
    body = current["body"] if body is None else body
    subject = current["subject"] if subject is None else subject
    body_html = current.get("body_html", "") if body_html is None else body_html
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
    result = {"body": text, "subject": "", "length": len(text), "sms_long": channel == ev.SMS and len(text) > SMS_SOFT_LIMIT,
              "html_document": ""}
    if channel == ev.EMAIL:
        validate_text(event_key, subject, what="موضوع")
        result["subject"] = render_text(subject, context)[0]
        fragment = ""
        if body_html:
            fragment, _ = render_html(event_key, clean_html_template(event_key, body_html), context)
        result["html_document"] = render_email_document(store, result["subject"], text, fragment)
    return result
