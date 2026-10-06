"""دسترسی و ویرایشِ ``PlatformConfiguration`` — تک رکوردِ تنظیماتِ پلتفرم.

خواندن همیشه از طریق ``get_platform_configuration()`` (کش‌شده) انجام
می‌شود، نه ``PlatformConfiguration.objects.get(pk=1)`` مستقیم — تا رندرِ
هر تمپلیت یک کوئری‌ی تازه نسازد (طبق خواسته‌ی §Section 2)."""

import json

from django.core.cache import cache

from apps.portal.models import (
    STEP_UP_ACTION_KEYS,
    PlatformAuditLogEntry,
    PlatformConfiguration,
)
from apps.stores.services.enamad_verification_service import (
    EnamadBadgeError,
    EnamadVerificationMetaError,
    parse_enamad_badge_identifiers,
    parse_enamad_verification_meta_tag,
)

_CACHE_KEY = "portal:platform_configuration"
_CACHE_TIMEOUT = 300

_FORBIDDEN_KEYS = frozenset({
    "password", "password1", "password2", "new_password", "old_password",
    "token", "access_token", "refresh_token", "auth_token", "csrf_token",
    "secret", "api_key", "api_secret", "gateway_secret", "merchant_secret",
})


def _redact(value):
    if isinstance(value, dict):
        return {
            key: (_REDACTED if key.lower() in _FORBIDDEN_KEYS else _redact(val))
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


_REDACTED = "***REDACTED***"


def _summarize(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(_redact(value), ensure_ascii=False, default=str, sort_keys=True)
    except TypeError:
        return str(value)


def record_platform_audit_event(
    *, action_code: str, actor=None, object_type: str = "", object_id="",
    object_label: str = "", before=None, after=None, metadata: dict | None = None,
    result: str = PlatformAuditLogEntry.ResultStatus.SUCCESS,
) -> PlatformAuditLogEntry:
    return PlatformAuditLogEntry.objects.create(
        actor=actor, action_code=action_code, object_type=object_type,
        object_id=str(object_id) if object_id not in (None, "") else "",
        object_label=object_label, before_summary=_summarize(before),
        after_summary=_summarize(after), metadata=_redact(metadata or {}), result=result,
    )


def get_platform_configuration() -> PlatformConfiguration:
    config = cache.get(_CACHE_KEY)
    if config is not None:
        return config
    config, _created = PlatformConfiguration.objects.get_or_create(pk=1)
    cache.set(_CACHE_KEY, config, _CACHE_TIMEOUT)
    return config


def is_new_store_registration_enabled() -> bool:
    """سیاستِ «ثبت‌نامِ فروشگاهِ تازه» را **مستقیم از دیتابیس** می‌خواند، نه از
    کشِ ۵دقیقه‌ایِ ``get_platform_configuration`` — کشِ پیش‌فرض LocMem و
    per-process است و یک worker ممکن بود تا ۵ دقیقه پس از بستنِ ثبت‌نام هنوز
    آن را باز ببیند. این یک تصمیمِ اجرایی (enforcement) است، نه نمایش.
    اگر رکوردِ تنظیمات هنوز وجود نداشته باشد، پیش‌فرضِ مدل (فعال) است."""
    row = PlatformConfiguration.objects.filter(pk=1).values_list(
        "new_store_registration_enabled", flat=True,
    ).first()
    return True if row is None else bool(row)


class PlatformConfigurationError(Exception):
    """مقدارِ نامعتبر برای تنظیمات پلتفرم."""


def update_platform_configuration(*, actor, **fields) -> PlatformConfiguration:
    """فیلدهای مجاز را روی تک‌رکوردِ تنظیمات می‌نویسد، اعتبارسنجی می‌کند،
    کش را باطل می‌کند، و رخدادِ حسابرسی ثبت می‌کند."""
    if "deletion_retention_days" in fields:
        days = fields["deletion_retention_days"]
        if not (180 <= days <= 365):
            raise PlatformConfigurationError("روزهای نگهداری باید بین ۱۸۰ تا ۳۶۵ باشد.")

    if "step_up_actions" in fields:
        unknown = set(fields["step_up_actions"]) - STEP_UP_ACTION_KEYS
        if unknown:
            raise PlatformConfigurationError(f"کلید(های) نامعتبر در سیاست تأیید مجدد: {sorted(unknown)}")

    if "enamad_verification_meta_tag" in fields:
        value = str(fields["enamad_verification_meta_tag"] or "").strip()
        if value:
            try:
                parse_enamad_verification_meta_tag(value)
            except EnamadVerificationMetaError as exc:
                raise PlatformConfigurationError(str(exc)) from exc
        fields["enamad_verification_meta_tag"] = value

    if "enamad_id" in fields or "enamad_auth_code" in fields:
        current = get_platform_configuration()
        enamad_id = str(fields.get("enamad_id", current.enamad_id) or "").strip()
        auth_code = str(fields.get("enamad_auth_code", current.enamad_auth_code) or "").strip()
        try:
            parse_enamad_badge_identifiers(enamad_id, auth_code)
        except EnamadBadgeError as exc:
            raise PlatformConfigurationError(str(exc)) from exc
        fields["enamad_id"] = enamad_id
        fields["enamad_auth_code"] = auth_code

    config = get_platform_configuration()

    if "step_up_actions" in fields:
        # Merge (PATCH semantics), never a full replace — toggling one
        # sensitive action's step-up requirement must not silently disable
        # step-up for every other action already configured.
        merged = dict(config.step_up_actions)
        merged.update(fields["step_up_actions"])
        fields = {**fields, "step_up_actions": merged}

    before = {name: getattr(config, name) for name in fields}

    for name, value in fields.items():
        setattr(config, name, value)
    config.save()

    cache.delete(_CACHE_KEY)

    record_platform_audit_event(
        actor=actor, action_code="platform_configuration.updated",
        object_type="PlatformConfiguration", object_id=1,
        before=before, after=fields,
    )
    return config
