"""رندر قالب، کنترل اعتبار، ارسال و ثبت تاریخچه پیامک."""

import logging
import secrets

from django.utils import timezone

from apps.core.models import ShopSettings

from ..events import DEFAULT_TEMPLATES, EVENT_VARIABLES, SmsEvent
from ..models import SmsLog, SmsOutboxItem, SmsTemplate
from . import template_renderer
from .backends import MelipayamakBackend, SmsBackend, SmsRastiBackend
from .billing_policy_service import (
    InsufficientSmsCreditError, quote_message, refund_credits, reserve_credits,
)

logger = logging.getLogger(__name__)


class SmsTemplateError(Exception):
    pass


def validate_template_body(event_key: str, body: str) -> None:
    """اعتبارسنجیِ سخت‌گیرانه (S2): فقط ``{متغیرِ مجاز}`` و ``{{``/``}}``؛ هر ساختارِ
    دیگر (``{x.y}``، ``{x[0]}``، ``{x:fmt}``، آکولادِ تنها…) رد می‌شود."""
    allowed = EVENT_VARIABLES.get(event_key, {})
    try:
        template_renderer.validate(body, allowed)
    except template_renderer.StrictTemplateError as exc:
        if exc.kind == "unknown":
            allowed_list = "، ".join(f"{{{k}}}" for k in allowed) or "—"
            raise SmsTemplateError(
                f"متغیر ناشناخته در قالب: {{{'، '.join(exc.names)}}}. "
                f"متغیرهای مجاز این رویداد: {allowed_list}"
            ) from exc
        raise SmsTemplateError(str(exc)) from exc


def _mirror_history(log, *, context=None, is_test=False):
    """S0: آینه‌ی فقط‌تاریخچه در ``apps.notifications`` (ارسال همچنان همزمان/قدیمی؛
    هرگز استثنا نمی‌دهد و ارسال دوباره‌ای ایجاد نمی‌کند)."""
    from apps.notifications.services.legacy_history import safe_record_legacy_sms

    return safe_record_legacy_sms(log, context=context, is_test=is_test)


def get_backend(*, store) -> SmsBackend:
    shop = ShopSettings.load(store=store)
    if shop.sms_backend == ShopSettings.SmsBackend.SMSRASTI:
        return SmsRastiBackend(store=store, device_token=shop.smsrasti_device_token or "")
    from apps.portal.services.owner_sms_service import get_platform_sms_backend
    return get_platform_sms_backend()


def regenerate_smsrasti_device_token(*, store) -> str:
    shop = ShopSettings.load(store=store)
    shop.smsrasti_device_token = secrets.token_urlsafe(32)
    shop.save(update_fields=["smsrasti_device_token", "updated_at"])
    return shop.smsrasti_device_token


def _render(template: SmsTemplate, context: dict, shop_name: str, *, fallback_unsafe: bool = False) -> str:
    """رندرِ امن. ``fallback_unsafe``: برایِ ارسالِ واقعی — قالبِ ذخیره‌شده‌ای که
    ساختارِ غیرمجازِ قدیمی دارد (و قبلاً با ``str.format`` رندر می‌شد) نباید ارسالِ
    پیامکِ آن رویداد را متوقف کند؛ متنِ پیش‌فرضِ همان رویداد جایگزین و خطا لاگ
    می‌شود. متغیرِ ناشناخته مثلِ قبل خطا می‌دهد (ارسال نمی‌شود)."""
    allowed = EVENT_VARIABLES.get(template.event_key, {})
    defaults = dict.fromkeys(allowed, "")
    full_context = {**defaults, **context, "shop_name": shop_name}
    body = template.body
    try:
        template_renderer.validate(body, allowed)
    except template_renderer.StrictTemplateError as exc:
        if exc.kind == "syntax" and fallback_unsafe and template.event_key in DEFAULT_TEMPLATES:
            logger.error(
                "SmsTemplate %s (event=%s) has unsafe syntax (%s); using default text. "
                "Run `manage.py audit_sms_templates`.", template.pk, template.event_key, exc,
            )
            body = DEFAULT_TEMPLATES[template.event_key]
        else:
            validate_template_body(template.event_key, body)
            raise SmsTemplateError(str(exc)) from exc
    return template_renderer.render(body, full_context, allowed)


def _dispatch(*, event_key: str, phone: str, message: str, store, template=None, context=None) -> SmsLog:
    is_otp = event_key == SmsEvent.OTP
    quote = quote_message(message)
    log = SmsLog.objects.create(
        store=store, event_key=event_key, recipient=phone,
        message="" if is_otp else message, status=SmsLog.Status.PENDING,
        character_count=quote.character_count, billable_units=quote.billable_units,
        unit_price_toman=quote.unit_price_toman, cost_toman=0,
    )
    # اول اعتبار را اتمیک رزرو می‌کنیم؛ فروشگاهِ بی‌اعتبار حتی نباید به
    # مرحله‌ی resolve/تماس Provider برای پیام عادی برسد. OTP هم مستقل از
    # انتخاب SmsRastiِ فروشگاه از Provider آنلاین مرکزی عبور می‌کند.
    backend = None

    try:
        before, reserved_after = reserve_credits(
            store=store, units=quote.billable_units, is_otp=is_otp,
        )
        log.balance_before = before
        log.balance_after = reserved_after
    except InsufficientSmsCreditError as exc:
        log.status = SmsLog.Status.FAILED
        log.error_message = (
            "اعتبار پیامک کافی نیست" if not is_otp else
            "سقف بدهی مجاز OTP تکمیل شده است؛ اعتبار پیامک را شارژ کنید"
        )
        log.balance_before = exc.balance
        log.balance_after = exc.balance
        log.save(update_fields=[
            "status", "error_message", "balance_before", "balance_after", "updated_at",
        ])
        return log

    if not is_otp:
        backend = get_backend(store=store)

    if is_otp:
        from apps.portal.services.owner_sms_service import send_platform_otp
        code = str((context or {}).get("otp_code", ""))
        result = send_platform_otp(
            to=phone, code=code, purpose="store_customer_otp",
            template_event_key=SmsEvent.OTP,
        )
    else:
        # اگر برای همین رویداد BodyId ملی‌پیامک تعریف شده باشد، ارسال واقعی
        # هم از Pattern خدماتی استفاده می‌کند؛ BodyId در پنل صرفاً تزئینی نیست.
        if isinstance(backend, MelipayamakBackend) and template is not None and template.melipayamak_body_id:
            result = backend.send_pattern(
                to=phone, body_id=template.melipayamak_body_id,
                variables=context or {},
                variables_order=template.melipayamak_variables_order or "otp_code",
            )
            result.provider = "melipayamak"
        else:
            result = backend.send(to=phone, text=message)
            if not getattr(result, "provider", ""):
                result.provider = getattr(backend, "provider_code", "")

    log.attempt_count = 1
    log.provider = getattr(result, "provider", "") or getattr(backend, "provider_code", "")
    if result.success:
        log.status = SmsLog.Status.SENT
        log.provider_ref_id = result.provider_ref_id
        log.sent_at = timezone.now()
        log.cost_toman = quote.cost_toman
    else:
        refunded = refund_credits(store=store, units=quote.billable_units)
        log.status = SmsLog.Status.FAILED
        log.error_message = result.error_message
        log.balance_after = refunded
    log.save(update_fields=[
        "status", "provider", "provider_ref_id", "error_message", "attempt_count",
        "sent_at", "cost_toman", "balance_before", "balance_after", "updated_at",
    ])
    return log


def send_event_sms(event_key: str, phone: str, context: dict | None = None, *, store) -> SmsLog | None:
    if store is None:
        logger.error("send_event_sms called with store=None for event=%s phone=%s", event_key, phone)
        return None
    try:
        shop = ShopSettings.load(store=store)
        if not shop.sms_enabled:
            return None
        template = SmsTemplate.objects.filter(event_key=event_key, is_active=True).first()
        if template is None:
            return None
        effective_context = context or {}
        if event_key == SmsEvent.OTP:
            effective_context = {"expire_minutes": "2", **effective_context}
        message = _render(template, effective_context, shop.name, fallback_unsafe=True)
        # Provider Pattern باید همان مقادیر نهایی رندر را داشته باشد؛ نام فروشگاه
        # همیشه از ShopSettings می‌آید و ورودی caller نمی‌تواند آن را جعل کند.
        provider_context = {**effective_context, "shop_name": shop.name}
        log = _dispatch(
            event_key=event_key, phone=phone, message=message, store=store,
            template=template, context=provider_context,
        )
        _mirror_history(log, context=provider_context)
        return log
    except Exception:
        logger.exception("send_event_sms failed for event=%s phone=%s store=%s", event_key, phone, store.slug)
        return None


def send_raw_sms(*, phone: str, message: str, store, event_key: str = SmsEvent.NOTIFICATION) -> SmsLog | None:
    """ارسال متن آماده‌ی Store با همان دروازه‌ی اعتبار/لاگ مرکزی.

    برای اعلان‌هایی است که متنشان بیرون از SmsTemplate ساخته می‌شود؛ هیچ مسیر
    Store-scoped مجاز نیست با ``send_platform_sms`` مستقیم، کنترل اعتبار را دور بزند.
    """
    if store is None or not message:
        return None
    try:
        shop = ShopSettings.load(store=store)
        if not shop.sms_enabled:
            return None
        return _dispatch(
            event_key=event_key, phone=phone, message=message, store=store,
            template=None, context={},
        )
    except Exception:
        logger.exception("send_raw_sms failed for event=%s phone=%s store=%s", event_key, phone, store.slug)
        return None


DUMMY_TEST_CONTEXT = {
    "customer_name": "کاربر آزمایشی", "order_code": "TEST-00000",
    "amount": "۱۰۰٬۰۰۰", "tracking_code": "TEST-TRACK-123",
    "otp_code": "۱۲۳۴۵۶", "expire_minutes": "2",
}


def send_test_sms(*, event_key: str, phone: str, store) -> SmsLog:
    template = SmsTemplate.objects.filter(event_key=event_key).first()
    if template is None:
        raise SmsTemplateError("قالبی برای این رویداد یافت نشد")
    shop = ShopSettings.load(store=store)
    message = _render(template, DUMMY_TEST_CONTEXT, shop.name)
    provider_context = {**DUMMY_TEST_CONTEXT, "shop_name": shop.name}
    log = _dispatch(
        event_key=event_key, phone=phone, message=message, store=store,
        template=template, context=provider_context,
    )
    _mirror_history(log, context=provider_context, is_test=True)
    return log


class RetryNotEligibleError(Exception):
    pass


def retry_failed_log(*, log_id: int, store) -> SmsLog:
    try:
        log = SmsLog.objects.get(pk=log_id, store=store)
    except SmsLog.DoesNotExist as exc:
        raise RetryNotEligibleError("گزارشی با این شناسه برای این فروشگاه یافت نشد") from exc
    if log.status != SmsLog.Status.FAILED:
        raise RetryNotEligibleError("فقط پیامک‌های ناموفق قابل ارسال دوباره‌اند")
    if log.event_key == SmsEvent.OTP:
        raise RetryNotEligibleError("OTP قدیمی قابل ارسال دوباره نیست؛ کد تازه درخواست کنید")

    quote = quote_message(log.message)
    try:
        before, reserved_after = reserve_credits(store=store, units=quote.billable_units, is_otp=False)
    except InsufficientSmsCreditError:
        log.error_message = "اعتبار پیامک کافی نیست"
        log.save(update_fields=["error_message", "updated_at"])
        return log

    backend = get_backend(store=store)
    result = backend.send(to=log.recipient, text=log.message)
    if not getattr(result, "provider", ""):
        result.provider = getattr(backend, "provider_code", "")
    log.attempt_count += 1
    log.provider = result.provider
    log.character_count = quote.character_count
    log.billable_units = quote.billable_units
    log.unit_price_toman = quote.unit_price_toman
    log.balance_before = before
    if result.success:
        log.status = SmsLog.Status.SENT
        log.provider_ref_id = result.provider_ref_id
        log.error_message = ""
        log.sent_at = timezone.now()
        log.cost_toman = quote.cost_toman
        log.balance_after = reserved_after
    else:
        log.status = SmsLog.Status.FAILED
        log.error_message = result.error_message
        log.balance_after = refund_credits(store=store, units=quote.billable_units)
        log.cost_toman = 0
    log.save(update_fields=[
        "status", "provider", "provider_ref_id", "error_message", "attempt_count",
        "sent_at", "character_count", "billable_units", "unit_price_toman",
        "cost_toman", "balance_before", "balance_after", "updated_at",
    ])
    _mirror_history(log)
    return log


def retry_smsrasti_outbox_item(*, item_id: int, store) -> SmsOutboxItem:
    try:
        item = SmsOutboxItem.objects.get(pk=item_id, store=store)
    except SmsOutboxItem.DoesNotExist as exc:
        raise RetryNotEligibleError("آیتمی با این شناسه برای این فروشگاه یافت نشد") from exc
    if item.status != SmsOutboxItem.Status.FAILED:
        raise RetryNotEligibleError("فقط آیتم‌های ناموفق قابل صف‌شدن دوباره‌اند")
    item.status = SmsOutboxItem.Status.PENDING
    item.error_message = ""
    item.claimed_at = None
    item.save(update_fields=["status", "error_message", "claimed_at", "updated_at"])
    return item
