"""ارسال مرکزی پیامک پلتفرم با ملی‌پیامک اصلی و کاوه‌نگار رزرو."""

import logging

from django.conf import settings

from apps.sms.events import SmsEvent
from apps.sms.services.backends import (
    ConsoleBackend, KavenegarBackend, MelipayamakBackend, SmsBackend, SmsSendResult, UnavailableBackend,
)

logger = logging.getLogger(__name__)


def _truthy(value, default=False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _platform_config():
    from apps.portal.services.platform_config_service import get_platform_configuration
    config = get_platform_configuration()
    return config, config.get_sms_credentials()


def _provider_enabled(credentials: dict, provider: str) -> bool:
    key = f"{provider}_enabled"
    return _truthy(credentials.get(key), default=True)


def get_platform_sms_backend(provider: str | None = None) -> SmsBackend:
    config, credentials = _platform_config()
    selected = provider or (config.sms_backend if config.sms_backend and config.sms_backend != "console" else settings.RASTISI_OWNER_SMS_BACKEND)

    if selected == "melipayamak" and _provider_enabled(credentials, "melipayamak"):
        username = credentials.get("melipayamak_username") or settings.RASTISI_OWNER_SMS_USERNAME
        password = credentials.get("melipayamak_password") or settings.RASTISI_OWNER_SMS_PASSWORD
        sender = credentials.get("melipayamak_sender") or config.sms_sender_number or settings.RASTISI_OWNER_SMS_SENDER
        return MelipayamakBackend(username=username, password=password, sender=sender)

    if selected == "kavenegar" and _provider_enabled(credentials, "kavenegar"):
        api_key = credentials.get("kavenegar_api_key") or settings.RASTISI_OWNER_SMS_API_KEY
        sender = credentials.get("kavenegar_sender") or config.sms_sender_number or settings.RASTISI_OWNER_SMS_SENDER
        return KavenegarBackend(api_key=api_key, sender=sender)

    if selected in {"melipayamak", "kavenegar"}:
        return UnavailableBackend(
            provider_code=selected, error_message="شرکت پیامکی انتخاب‌شده غیرفعال است",
        )
    # «console» هرگز نباید در production «ارسال‌شده + کسرِ اعتبار» ثبت کند: فقط وقتی مجاز است که صریحاً اجازه
    # داده شده باشد (تست/توسعه — همان پرچمِ OTP)؛ وگرنه شکستِ صریح با پیامِ قابل‌اقدام.
    if settings.RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP:
        return ConsoleBackend()
    return UnavailableBackend(
        provider_code="console",
        error_message="درگاه پیامکِ مرکزیِ پلتفرم پیکربندی نشده است؛ به پشتیبانی پلتفرم اطلاع دهید",
    )


def describe_platform_backend() -> dict:
    """سلامتِ درگاهِ مرکزیِ پلتفرم بر پایه‌ی **همان** تصمیمی که ارسال واقعاً می‌گیرد (برایِ پایش/``verify_delivery_channels``).
    → ``{"provider", "real", "problems": [..]}`` — بدونِ افشایِ رازها."""
    backend = get_platform_sms_backend()
    provider = getattr(backend, "provider_code", "") or "unknown"
    problems: list[str] = []
    if isinstance(backend, ConsoleBackend):
        problems.append("درگاه پلتفرم console است؛ پیامی واقعاً ارسال نمی‌شود")
    elif isinstance(backend, UnavailableBackend):
        problems.append(backend.error_message)
    elif isinstance(backend, MelipayamakBackend):
        if not (backend.username and backend.password):
            problems.append("نام‌کاربری/رمزِ ملی‌پیامکِ پلتفرم تنظیم نشده است")
        if not backend.sender:
            problems.append("شماره‌ی فرستنده‌ی پلتفرم تنظیم نشده است")
    elif isinstance(backend, KavenegarBackend):
        if not backend.api_key:
            problems.append("کلیدِ API کاوه‌نگارِ پلتفرم تنظیم نشده است")
        if not backend.sender:
            problems.append("شماره‌ی فرستنده‌ی پلتفرم تنظیم نشده است")
    return {"provider": provider, "real": not isinstance(backend, (ConsoleBackend, UnavailableBackend)), "problems": problems}


def send_platform_sms(*, to: str, text: str, provider: str | None = None) -> SmsSendResult:
    backend = get_platform_sms_backend(provider=provider)
    result = backend.send(to=to, text=text)
    result.provider = getattr(backend, "provider_code", "")
    if not result.success:
        logger.warning("platform SMS send failed: to=%s provider=%s error=%s", to, result.provider, result.error_message)
    return result


def _otp_runtime_config(template_event_key: str) -> dict:
    config, credentials = _platform_config()
    use_db_provider = bool(config.sms_backend and config.sms_backend != "console")
    provider = config.sms_backend if use_db_provider else settings.RASTISI_OWNER_SMS_BACKEND

    from apps.sms.models import SmsTemplate
    template = SmsTemplate.objects.filter(event_key=template_event_key).first()

    return {
        "provider": provider or "console",
        "melipayamak_enabled": _provider_enabled(credentials, "melipayamak"),
        "kavenegar_enabled": _provider_enabled(credentials, "kavenegar"),
        "username": credentials.get("melipayamak_username") or settings.RASTISI_OWNER_SMS_USERNAME,
        "password": credentials.get("melipayamak_password") or settings.RASTISI_OWNER_SMS_PASSWORD,
        "melipayamak_sender": credentials.get("melipayamak_sender") or config.sms_sender_number or settings.RASTISI_OWNER_SMS_SENDER,
        "body_id": (getattr(template, "melipayamak_body_id", "") or credentials.get("melipayamak_otp_body_id") or settings.RASTISI_OWNER_SMS_OTP_BODY_ID),
        "variables_order": (getattr(template, "melipayamak_variables_order", "") or credentials.get("melipayamak_otp_variables_order") or settings.RASTISI_OWNER_SMS_OTP_VARIABLES_ORDER or "otp_code"),
        "fallback_enabled": (_truthy(credentials.get("otp_fallback_enabled")) if "otp_fallback_enabled" in credentials else settings.RASTISI_OWNER_SMS_OTP_FALLBACK_ENABLED),
        "kavenegar_api_key": credentials.get("kavenegar_api_key") or settings.RASTISI_OWNER_SMS_API_KEY,
        "kavenegar_sender": credentials.get("kavenegar_sender") or config.sms_sender_number or settings.RASTISI_OWNER_SMS_SENDER,
        "kavenegar_template": (getattr(template, "kavenegar_template", "") or credentials.get("kavenegar_otp_template") or settings.RASTISI_OWNER_SMS_KAVENEGAR_OTP_TEMPLATE),
    }


def send_platform_otp(
    *, to: str, code: str, purpose: str = "otp", expire_minutes: int = 2,
    template_event_key: str = SmsEvent.PLATFORM_OWNER_OTP,
) -> SmsSendResult:
    """OTP provider-native؛ BodyId/Template از قالب همان رویداد خوانده می‌شود."""
    runtime = _otp_runtime_config(template_event_key)
    provider = runtime["provider"]

    if provider == "console":
        if settings.RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP:
            logger.debug("[OTP:console-test] suppressed real delivery to=%s", to)
            return SmsSendResult(success=True, provider_ref_id="console-test", provider="console")
        return SmsSendResult(success=False, error_message="درگاه واقعی OTP پیکربندی نشده است", provider="console")

    variables = {
        "otp_code": str(code), "code": str(code),
        "expire_minutes": str(expire_minutes), "purpose": str(purpose),
    }

    if provider == "kavenegar":
        if not runtime["kavenegar_enabled"]:
            return SmsSendResult(success=False, error_message="کاوه‌نگار غیرفعال است", provider="kavenegar")
        backend = KavenegarBackend(api_key=runtime["kavenegar_api_key"], sender=runtime["kavenegar_sender"])
        result = backend.send_verify_lookup(to=to, token=str(code), template=runtime["kavenegar_template"])
        result.provider = "kavenegar"
        if not result.success:
            logger.warning("platform OTP primary Kavenegar failed: to=%s error=%s", to, result.error_message)
        return result

    if provider != "melipayamak":
        return SmsSendResult(success=False, error_message=f"درگاه OTP ناشناخته است: {provider}", provider=provider)

    if not runtime["melipayamak_enabled"]:
        primary_result = SmsSendResult(success=False, error_message="ملی‌پیامک غیرفعال است", provider="melipayamak")
    else:
        primary = MelipayamakBackend(username=runtime["username"], password=runtime["password"], sender=runtime["melipayamak_sender"])
        primary_result = primary.send_pattern(
            to=to, body_id=runtime["body_id"], variables=variables,
            variables_order=runtime["variables_order"],
        )
        primary_result.provider = "melipayamak"
    if primary_result.success:
        return primary_result

    logger.warning("platform OTP Melipayamak failed: to=%s error=%s", to, primary_result.error_message)
    if not runtime["fallback_enabled"] or not runtime["kavenegar_enabled"]:
        return primary_result

    fallback = KavenegarBackend(api_key=runtime["kavenegar_api_key"], sender=runtime["kavenegar_sender"])
    fallback_result = fallback.send_verify_lookup(to=to, token=str(code), template=runtime["kavenegar_template"])
    fallback_result.provider = "kavenegar"
    if fallback_result.success:
        return fallback_result

    logger.warning("platform OTP Kavenegar fallback failed: to=%s error=%s", to, fallback_result.error_message)
    return SmsSendResult(
        success=False, provider="kavenegar",
        error_message=("ملی‌پیامک: " + (primary_result.error_message or "ناموفق") + " | کاوه‌نگار: " + (fallback_result.error_message or "ناموفق")),
    )
