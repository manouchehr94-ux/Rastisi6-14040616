"""پلِ میانِ واژگانِ متغیرِ قالب‌هایِ پیامکِ قدیمی (``apps.sms``) و سیستمِ اعلان (S1).

قالبِ پیامکِ رویدادهایِ دارایِ ``legacy_sms_event`` همچنان در ``SmsTemplate`` (تنها
منبعِ حقیقتِ ارسالِ واقعی) ذخیره می‌شود؛ ویرایشگرِ یکپارچه متن را با نامِ متغیرهایِ
جدید نشان می‌دهد/می‌گیرد و با این نگاشتِ یک‌به‌یک به/از نامِ قدیمی تبدیل می‌کند.
نگاشت باید برایِ هر رویداد دوسویه (bijective) و کامل باشد — تستِ سازگاری این را
تضمین می‌کند."""

from __future__ import annotations

from apps.notifications import events as ev
from apps.sms.events import EVENT_VARIABLES
from apps.sms.services import template_renderer

# نامِ قدیمی → نامِ جدید (متغیرهایی که اینجا نیستند هم‌نام‌اند)
_ALIASES = {
    "order_code": "order_number",
    "amount": "order_total",
    "shop_name": "store_name",
    "tracking_code": "tracking_number",
}


class LegacyTemplateError(ValueError):
    pass


def legacy_to_new_map(legacy_event: str) -> dict:
    return {name: _ALIASES.get(name, name) for name in EVENT_VARIABLES.get(legacy_event, {})}


def new_to_legacy_map(legacy_event: str) -> dict:
    return {new: old for old, new in legacy_to_new_map(legacy_event).items()}


def allowed_new_variables(legacy_event: str) -> set:
    return set(legacy_to_new_map(legacy_event).values())


def body_to_new(legacy_event: str, body: str) -> str:
    """متنِ ذخیره‌شده (واژگانِ قدیمی) → متنِ نمایشیِ ویرایشگر (واژگانِ جدید).
    اگر متن ساختارِ غیرمجاز دارد، همان‌طور برگردانده می‌شود (ویرایشگر خطا نشان می‌دهد)."""
    try:
        return template_renderer.rename_placeholders(body, legacy_to_new_map(legacy_event))
    except template_renderer.StrictTemplateError:
        return body


def body_to_legacy(legacy_event: str, body: str) -> str:
    """متنِ ویرایشگر (واژگانِ جدید) → متنِ قابلِ ذخیره در ``SmsTemplate``. متغیرِ بدونِ
    معادلِ قدیمی (مثلاً ``{order_url}``) یا ساختارِ غیرمجاز → ``LegacyTemplateError``."""
    mapping = new_to_legacy_map(legacy_event)
    try:
        names = template_renderer.placeholders(body)
    except template_renderer.StrictTemplateError as exc:
        raise LegacyTemplateError(str(exc)) from exc
    unsupported = sorted({n for n in names if n not in mapping})
    if unsupported:
        raise LegacyTemplateError(
            "متغیر در پیامکِ این رویداد پشتیبانی نمی‌شود: " + "، ".join("{" + n + "}" for n in unsupported)
            + ". متغیرهای مجاز: " + "، ".join("{" + n + "}" for n in sorted(mapping))
        )
    return template_renderer.rename_placeholders(body, mapping)


def legacy_event_of(event_key: str) -> str:
    event = ev.EVENTS.get(event_key)
    return event.legacy_sms_event if event else ""
