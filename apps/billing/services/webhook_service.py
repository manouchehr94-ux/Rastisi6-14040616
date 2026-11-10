"""پذیرشِ Webhookِ صورتحساب (ADR-76).

جریان: بررسیِ اندازه → تأییدِ امضا (پیش از هر تغییرِ کسب‌وکاری) → تجزیه →
حذفِ تکراری (قیدِ یکتا) → ذخیره‌ی پاک‌سازی‌شده → واگذاریِ پردازش به
``confirmation_service`` (که تراکنشی و idempotent است؛ در commit 5 وصل
می‌شود). امضایِ نامعتبر/بدنه‌ی بزرگ هرگز چیزی را در دامنه تغییر نمی‌دهد."""

import hashlib

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing.models import BillingWebhookEvent
from apps.billing.providers import registry
from apps.billing.providers.base import ProviderResponseError, WebhookVerificationError

#: کلیدهایی که هرگز نباید در payloadِ ذخیره‌شده بمانند (ردکت می‌شوند).
SENSITIVE_KEYS = frozenset({
    "card", "card_number", "pan", "cvv", "cvc", "secret", "password",
    "authorization", "token", "api_key", "apikey", "signature", "access_token",
})
_REDACTED = "***"


class WebhookError(Exception):
    """خطای پذیرشِ Webhook (پیامِ امن)."""


class WebhookTooLarge(WebhookError):
    """بدنه‌ی Webhook از حدِ مجاز بزرگ‌تر است."""


def _redact(value):
    """کلیدهایِ حساس را به‌صورتِ بازگشتی ردکت می‌کند."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if str(k).lower() in SENSITIVE_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _max_bytes() -> int:
    return getattr(settings, "RASTISI_BILLING_MAX_WEBHOOK_BYTES", 65536)


@transaction.atomic
def ingest_webhook(*, provider_code, headers, body: bytes, now=None):
    """یک Webhook را می‌پذیرد و ردیفِ ``BillingWebhookEvent`` را برمی‌گرداند.
    تحویلِ تکراری همان ردیفِ موجود را برمی‌گرداند (idempotent). امضا/اندازه‌ی
    نامعتبر استثنا می‌اندازد و هیچ ردیفی نمی‌سازد."""
    now = now or timezone.now()
    if len(body) > _max_bytes():
        raise WebhookTooLarge("بدنه‌ی Webhook بیش از حدِ مجاز است.")

    provider = registry.get_provider(provider_code)
    secret = registry.webhook_secret()
    # امضا پیش از هر تغییرِ کسب‌وکاری تأیید می‌شود؛ شکست ⇒ استثنا، بدونِ ذخیره.
    provider.verify_webhook(headers=headers, body=body, secret=secret)

    event_data = provider.parse_webhook_event(body=body)
    if not event_data.event_id:
        raise ProviderResponseError("رخدادِ Webhook شناسه ندارد.", code="no_event_id")

    payload_hash = hashlib.sha256(body).hexdigest()

    # حذفِ تکراری: قیدِ یکتا رویِ (provider, external_event_id).
    existing = BillingWebhookEvent.objects.select_for_update().filter(
        provider=provider.code, external_event_id=event_data.event_id,
    ).first()
    if existing is not None:
        return existing

    import json
    try:
        raw = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raw = {}

    try:
        # The INSERT runs in its own savepoint. A unique-constraint violation inside the OUTER atomic block would otherwise
        # leave that transaction marked for rollback, and the re-query below would raise TransactionManagementError (an HTTP
        # 500 on a perfectly legitimate concurrent duplicate delivery) (F-15).
        with transaction.atomic():
            event = BillingWebhookEvent.objects.create(
                provider=provider.code, external_event_id=event_data.event_id,
                event_type=event_data.event_type, signature_valid=True,
                processing_status=BillingWebhookEvent.ProcessingStatus.RECEIVED,
                payload_hash=payload_hash, sanitized_payload=_redact(raw), received_at=now,
            )
    except IntegrityError:
        # مسابقه: تحویلِ هم‌زمانِ همان رخداد — ردیفِ موجود را برگردان.
        return BillingWebhookEvent.objects.get(
            provider=provider.code, external_event_id=event_data.event_id,
        )
    return event


def mark_processed(event, *, now=None):
    """RECEIVED/FAILED/IGNORED -> PROCESSED. Idempotent; a processed event stays processed."""
    now = now or timezone.now()
    BillingWebhookEvent.objects.filter(pk=event.pk).update(
        processing_status=BillingWebhookEvent.ProcessingStatus.PROCESSED, processed_at=now, error_summary="", updated_at=now,
    )
    event.refresh_from_db()
    return event


def mark_failed(event, *, error, now=None):
    """Record a failure. A PROCESSED event is terminal: a stale or late writer can never move it back to FAILED (F-17).
    The conditional UPDATE is atomic, so concurrent workers cannot overwrite each other's terminal state."""
    now = now or timezone.now()
    from django.db.models import F

    BillingWebhookEvent.objects.filter(pk=event.pk).exclude(
        processing_status=BillingWebhookEvent.ProcessingStatus.PROCESSED,
    ).update(
        processing_status=BillingWebhookEvent.ProcessingStatus.FAILED, processed_at=now,
        error_summary=str(error)[:300], retry_count=F("retry_count") + 1, updated_at=now,
    )
    event.refresh_from_db()
    return event


def record_unexpected_failure(event, exc, *, now=None):
    """Durably record an unexpected processing error WITHOUT ever raising (it runs in an error path). Only the exception
    class name is stored: no payload, no message that could carry sensitive data."""
    try:
        return mark_failed(event, error=f"unexpected:{type(exc).__name__}", now=now)
    except Exception:  # noqa: BLE001 — the caller is already handling a failure; recording it is best-effort but attempted
        import logging

        logging.getLogger("billing").exception("could not record webhook failure for event %s", getattr(event, "pk", "?"))
        return event
