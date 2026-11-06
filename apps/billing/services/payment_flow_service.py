"""جریانِ hosted-payment و پردازشِ رخدادِ Webhookِ تأییدشده (ADR-77).

- ``start_payment``: یک تلاش می‌سازد، جلسه‌ی Provider را ایجاد و فاکتور را به
  ``payment_pending`` می‌برد، سپس اطلاعاتِ redirect را برمی‌گرداند.
- ``process_webhook_event``: یک ``BillingWebhookEvent`` تأییدشده را به
  ``confirmation_service`` وصل می‌کند (idempotent). بازگشتِ مرورگر هرگز مدرکِ
  پرداخت نیست — فقط این مسیر یا اقدامِ صریحِ مدیر پرداخت را تأیید می‌کند."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    BillingWebhookEvent,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
)
from apps.billing.providers import registry
from apps.billing.providers.base import BillingProviderError
from apps.billing.services import attempt_service, webhook_service
from apps.billing.services.confirmation_service import ConfirmationError, confirm_payment


class PaymentFlowError(Exception):
    """خطای قابل‌نمایش هنگام شروعِ پرداخت."""


def _storable_extra(extra) -> dict:
    """فقط مقدارهای ساده‌ی JSON از جلسه‌ی Provider (مثلاً ``urlId``)؛ بدونِ هیچ رازی."""
    return {str(k)[:40]: v for k, v in dict(extra or {}).items() if isinstance(v, (str, int, bool)) and len(str(v)) <= 200}


def gateway_redirect(provider_code: str, url: str, post_fields=None):
    """پاسخِ هدایتِ مرورگر به صفحه‌ی پرداختِ درگاه. درگاه‌هایی که Referer=دامنه‌ی پذیرنده می‌خواهند (پاسارگاد) از
    صفحه‌ی میانیِ ``referrer=origin`` عبور می‌کنند؛ بقیه یک ۳۰۲ ساده."""
    from apps.orders.gateways.redirects import gateway_redirect_response
    from apps.orders.gateways.registry import get_adapter

    try:
        adapter = get_adapter(provider_code)
    except KeyError:
        adapter = None
    return gateway_redirect_response(url, adapter=adapter, post_fields=post_fields)


def callback_url_for(callback_base_url: str, attempt) -> str:
    """آدرسِ بازگشتِ عمومیِ یک تلاش (``/billing/return/<token>/``) — توکنِ غیرقابلِ‌حدس؛ احرازِ
    نشست لازم نیست (وضعیت فقط با verify سرور-به-سرور تعیین می‌شود)."""
    return f"{callback_base_url.rstrip('/')}/billing/return/{attempt.public_token}/"


def safe_return_to(value: str) -> str:
    """مقصدِ بازگشتِ کاربر پس از verify: مسیرِ نسبیِ هم‌میزبان، یا URLِ مطلقِ http(s) که میزبانش در
    ``ALLOWED_HOSTS`` باشد (داشبوردِ هر فروشگاه روی میزبانِ خودش است و callback روی میزبانِ پلتفرم).
    هر چیزِ دیگر (میزبانِ بیگانه، ``//``، backslash، کاراکترِ کنترلی، userinfo) رد می‌شود ⇒ open-redirect ممنوع."""
    from urllib.parse import urlsplit

    from django.conf import settings
    from django.http.request import validate_host

    value = (value or "").strip()
    if not value or len(value) > 500 or "\\" in value or any(ord(c) < 32 for c in value):
        return ""
    if value.startswith("/"):
        return "" if value.startswith("//") else value
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not host or parts.username is not None or parts.password is not None:
        return ""
    return value if validate_host(host, settings.ALLOWED_HOSTS) else ""


def start_payment(invoice, *, return_url="", actor=None, idempotency_key="", now=None,
                  callback_base_url="", return_to="", provider=None):
    """یک تلاشِ پرداخت و جلسه‌ی Provider برایِ یک فاکتورِ قابلِ‌پرداخت می‌سازد و
    فاکتور را به ``payment_pending`` می‌برد. ``(attempt, session)`` را برمی‌گرداند.

    دفاعِ لایه‌ای برایِ ``PLAN_CHANGE`` (SUB-001 Repair 3، Blocker 4): پیش از
    شروعِ پرداخت، اگر فاکتور از نوعِ ``PLAN_CHANGE`` باشد، تازگیِ *همانِ*
    اثرانگشتِ منبع/هدفی که هنگامِ ساختنِ فاکتور رویِ ``idempotency_key``اش
    نوشته شده دوباره بررسی می‌شود (همانندِ محافظتِ پیش‌نمایشِ کهنه‌یِ 5A، فقط
    این‌بار در لحظه‌یِ شروعِ پرداخت، نه لحظه‌یِ ساختنِ فاکتور). اگر اشتراک از
    زمانِ ساختنِ این فاکتور از یک مسیرِ دیگر (مثلاً اعمالِ یک
    ``ScheduledPlanChange`` هنگامِ تمدید) تغییرِ نسخه‌ی پلن کرده باشد، این
    فاکتور دیگر تصمیمِ معتبرِ فعلی نیست — پرداخت شروع نمی‌شود (خطا) تا پول
    بر اساسِ یک تصمیمِ کهنه جابه‌جا نشود. این بررسی صرفاً یک خوانشِ *بدونِ
    قفلِ اضافی* رویِ ``StoreSubscription`` است (نه ``select_for_update``) —
    قفلِ موجود در همین تابع فقط رویِ ``SubscriptionInvoice`` است، پس هیچ
    ترتیبِ قفلی معکوس نمی‌شود و رفتارِ ``INITIAL``/``RENEWAL`` دست‌نخورده
    می‌ماند (این بررسی فقط برایِ ``kind == PLAN_CHANGE`` اجرا می‌شود)."""
    now = now or timezone.now()
    failure = None
    with transaction.atomic():
        locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
        if not locked.is_payable:
            raise PaymentFlowError("این فاکتور در وضعیتِ قابلِ‌پرداخت نیست.")

        if locked.kind == SubscriptionInvoice.Kind.PLAN_CHANGE:
            from apps.subscriptions.models import StoreSubscription
            from apps.subscriptions.services import plan_change_service as pcs

            current_subscription = StoreSubscription.objects.get(pk=locked.subscription_id)
            expected = pcs._preview_token(current_subscription, locked.plan_version)
            if not locked.idempotency_key or locked.idempotency_key != expected:
                raise PaymentFlowError(
                    "این فاکتورِ تغییرِ پلن دیگر تصمیمِ معتبرِ فعلی نیست (اشتراک از "
                    "زمانِ ساختنِ این فاکتور تغییر کرده)؛ پرداخت شروع نمی‌شود."
                )

        attempt = attempt_service.create_attempt(
            locked, provider=provider, idempotency_key=idempotency_key, actor=actor, now=now,
        )
        attempt.return_to = safe_return_to(return_to)
        callback = callback_url_for(callback_base_url, attempt) if callback_base_url else return_url
        try:
            provider_obj = registry.get_provider(attempt.provider)
            session = provider_obj.create_payment_session(attempt=attempt, invoice=locked, return_url=callback)
        except BillingProviderError as exc:
            # شکستِ شروعِ پرداخت: تلاش به‌صورتِ ناموفق (با کدِ امن) ثبت می‌ماند؛ بدونِ هیچ رازی.
            attempt.status = SubscriptionPaymentAttempt.Status.FAILED
            attempt.failure_code = (exc.code or "provider_error")[:64]
            attempt.failure_message = "شروع پرداخت ناموفق بود."
            attempt.completed_at = now
            attempt.save(update_fields=["status", "failure_code", "failure_message", "completed_at", "return_to", "updated_at"])
            failure = exc
        else:
            attempt.provider_session_id = session.session_id
            attempt.provider_extra = _storable_extra(session.extra)
            attempt.status = SubscriptionPaymentAttempt.Status.PENDING
            attempt.save(update_fields=["provider_session_id", "provider_extra", "status", "return_to", "updated_at"])
            if locked.status in (SubscriptionInvoice.Status.OPEN, SubscriptionInvoice.Status.PAST_DUE):
                locked.status = SubscriptionInvoice.Status.PAYMENT_PENDING
                locked.save(update_fields=["status", "updated_at"])
    if failure is not None:
        raise PaymentFlowError(
            "درگاه پرداخت در دسترس نیست یا پیکربندی نشده است؛ کمی بعد دوباره تلاش کنید "
            f"(کد: {failure.code or 'provider_error'})."
        )
    return attempt, session


def flag_requires_action(attempt, *, code, now):
    """پولی که درگاه تأیید کرده امّا با رکوردِ ما نمی‌خواند (مبلغ/سفارش/پرداختِ تکراری): تلاش به
    «نیازمندِ اقدام» می‌رود تا در فهرستِ تطبیقِ مدیر دیده شود؛ هیچ اعمالِ مالی انجام نمی‌شود."""
    model = type(attempt)
    model.objects.filter(pk=attempt.pk).exclude(status=model.Status.SUCCEEDED).update(
        status=model.Status.REQUIRES_ACTION, failure_code=code[:64],
        failure_message="پرداخت تأیید شد امّا با رکورد مطابقت ندارد؛ نیازمندِ بررسیِ مدیر.",
        completed_at=now, updated_at=now,
    )


def verify_and_confirm(attempt, *, confirm, confirmation_error, actor=None, now=None, callback_data=None):
    """هسته‌یِ مشترکِ تأییدِ سرور-به-سرور برایِ هر «تلاشِ پرداختِ پلتفرم» (اشتراک یا بسته‌ی پیامک).

    بازگشتِ مرورگر هرگز مدرک نیست؛ فقط ``provider.verify_attempt`` موفقیت را اعلام می‌کند و سپس
    ``confirm`` (قفل، idempotent، بررسیِ مبلغ/ارز، اعمالِ یک‌بارِ اثر) صدا زده می‌شود. ``callback_data``
    فقط یک راهنماست: ادعای «ناموفق» در بازگشت *همراهِ* «verify سرور هم تأیید نکرد» تلاش را ناموفق
    علامت می‌زند (و بعداً هنوز قابلِ تأییدِ موفق است)."""
    now = now or timezone.now()
    model = type(attempt)
    S = model.Status
    if attempt.status == S.SUCCEEDED:
        return attempt
    if attempt.status == S.REQUIRES_ACTION and attempt.failure_code in ("duplicate_payment", "purchase_completed"):
        return attempt                                 # پرداختِ تکراریِ شناسایی‌شده؛ دوباره verify/حسابرسی نمی‌شود (تسویه با اقدامِ مدیرِ مالی)

    provider = registry.get_provider(attempt.provider)
    if not provider.supports_automatic_capture or not attempt.provider_session_id:
        return attempt

    try:
        status = provider.verify_attempt(attempt=attempt, callback_data=callback_data)
    except BillingProviderError as exc:
        if exc.code in ("amount_mismatch", "order_mismatch"):
            flag_requires_action(attempt, code=exc.code, now=now)
        elif exc.code == "provider_terminal_failure":
            model.objects.filter(pk=attempt.pk).exclude(status=S.SUCCEEDED).update(
                status=S.FAILED, failure_code="provider_terminal_failure",
                failure_message="ارائه‌دهنده اعلام کرد این تراکنش تکمیل نمی‌شود.", completed_at=now, updated_at=now,
            )
        raise
    if not status.succeeded:
        if provider.callback_claims_failure(callback_data) and attempt.status in (S.CREATED, S.PENDING):
            model.objects.filter(pk=attempt.pk, status__in=(S.CREATED, S.PENDING)).update(
                status=S.FAILED, failure_code="gateway_declined",
                failure_message="پرداخت توسطِ درگاه تأیید نشد.", completed_at=now, updated_at=now,
            )
            return model.objects.get(pk=attempt.pk)
        return attempt

    try:
        confirm(
            attempt=attempt, amount=status.amount, currency=status.currency or attempt.currency,
            provider_payment_id=status.provider_payment_id, actor=actor, now=now,
        )
    except confirmation_error:
        flag_requires_action(attempt, code="amount_mismatch", now=now)
        raise
    return model.objects.get(pk=attempt.pk)


def confirm_from_provider_verification(attempt, *, actor=None, now=None, callback_data=None):
    """تأییدِ سرور-به-سرورِ تلاشِ پرداختِ **اشتراک** (نگاه کنید به ``verify_and_confirm``)."""
    return verify_and_confirm(
        attempt, confirm=confirm_payment, confirmation_error=ConfirmationError,
        actor=actor, now=now, callback_data=callback_data,
    )


def process_webhook_event(event, *, actor=None, now=None):
    """یک رخدادِ Webhookِ ذخیره‌شده (امضا-تأییدشده) را پردازش می‌کند. idempotent:
    رخدادِ از قبل پردازش‌شده دوباره اعمال نمی‌شود."""
    now = now or timezone.now()
    if event.processing_status == BillingWebhookEvent.ProcessingStatus.PROCESSED:
        return event

    payload = event.sanitized_payload or {}
    event_type = event.event_type or payload.get("event_type", "")
    if event_type != "payment.succeeded":
        # رخدادِ غیرِ موفقیت — ثبت به‌عنوانِ نادیده‌گرفته‌شده (بدونِ تغییرِ مالی).
        event.processing_status = BillingWebhookEvent.ProcessingStatus.IGNORED
        event.processed_at = now
        event.save(update_fields=["processing_status", "processed_at", "updated_at"])
        return event

    session_id = str(payload.get("session_id", ""))
    provider_payment_id = str(payload.get("provider_payment_id", ""))
    currency = str(payload.get("currency", ""))
    try:
        amount = Decimal(str(payload.get("amount", "")))
    except (InvalidOperation, ValueError):
        return webhook_service.mark_failed(event, error="مبلغِ رخداد نامعتبر است.", now=now)

    attempt = SubscriptionPaymentAttempt.objects.filter(
        provider=event.provider, provider_session_id=session_id,
    ).first()
    if attempt is None:
        return webhook_service.mark_failed(event, error="تلاشِ پرداختِ مرتبط یافت نشد.", now=now)

    event.related_payment_attempt = attempt
    event.related_invoice_id = attempt.invoice_id
    event.save(update_fields=["related_payment_attempt", "related_invoice", "updated_at"])

    try:
        confirm_payment(
            attempt=attempt, amount=amount, currency=currency,
            provider_payment_id=provider_payment_id, actor=actor, now=now,
        )
    except ConfirmationError as exc:
        return webhook_service.mark_failed(event, error=str(exc), now=now)
    return webhook_service.mark_processed(event, now=now)
