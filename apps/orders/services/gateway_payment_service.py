"""Payment service — orchestrates real gateway payment lifecycle.

This service is the single entry point for:
1. Initiating a payment (online or COD)
2. Processing a gateway callback
3. Verifying and confirming a payment

It does NOT:
- Call gateway APIs directly (delegates to adapters)
- Modify Order status directly (delegates to order_service/payment_service)
- Resolve Store from request (caller's responsibility)
- Handle HTTP concerns (views' responsibility)

Concurrency guarantees:
- select_for_update on PaymentAttempt during verification
- Conditional status updates prevent double-processing
- Idempotency keys prevent duplicate attempts
- Already-paid order check prevents re-payment

State ownership:
- PaymentAttempt.status: owned by this service
- Order.payment_status: updated by this service on successful verification
- Order.status: transitions delegated to order_service.change_order_status
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.orders.encryption import CredentialEncryptionError
from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import GatewayError
from apps.orders.models import Order, PaymentAttempt, PaymentGatewayConfig, PaymentReconciliation, Transaction

logger = logging.getLogger("payment")

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PaymentServiceError(Exception):
    """Base for payment service errors — safe message for logs/admin."""


class PaymentAlreadyPaidError(PaymentServiceError):
    """Order is already paid."""


class OrderNotPayableError(PaymentServiceError):
    """Order can no longer be paid (e.g. it was canceled)."""


class PaymentConfigError(PaymentServiceError):
    """Gateway configuration is invalid or incomplete."""


class PaymentInitiationError(PaymentServiceError):
    """Failed to initiate payment with gateway."""


class PaymentVerificationFailed(PaymentServiceError):
    """Verification failed — order not marked paid."""


# ---------------------------------------------------------------------------
# Initiate payment
# ---------------------------------------------------------------------------


def initiate_payment(
    *,
    order: Order,
    gateway_config: PaymentGatewayConfig,
    callback_url: str,
    store,
    idempotency_key: str = "",
    pre_public_id: str = "",
) -> PaymentAttempt:
    """Create a PaymentAttempt and (for online gateways) request payment from gateway.

    Args:
        order: The finalized order to pay for.
        gateway_config: The active, configured gateway to use.
        callback_url: Full URL for gateway to redirect back to.
        store: Authoritative store instance.
        idempotency_key: Optional key to prevent duplicate attempts.
        pre_public_id: Optional pre-generated public_id (allows caller to build
                       the callback URL before the attempt is created).

    Returns:
        PaymentAttempt in REDIRECT_READY (online) or SUCCEEDED (COD) state.

    Raises:
        PaymentAlreadyPaidError: Order already paid.
        PaymentConfigError: Gateway not configured properly.
        PaymentInitiationError: Gateway rejected the request.
    """
    # Guard: re-read the authoritative state (the caller's object may be stale — e.g. the order was
    # canceled by staff or by the expiry job while the customer was on the payment page).
    current = Order.objects.filter(pk=order.pk).values("status", "payment_status").first()
    if current is not None:
        order.status, order.payment_status = current["status"], current["payment_status"]
    if order.status == Order.Status.CANCELED:
        raise OrderNotPayableError("این سفارش لغو شده و قابل پرداخت نیست")
    if order.payment_status == Order.PaymentStatus.PAID:
        raise PaymentAlreadyPaidError("این سفارش قبلاً پرداخت شده است")

    # Guard: gateway config belongs to this store
    if gateway_config.store_id != store.pk:
        raise PaymentConfigError("پیکربندی درگاه متعلق به این فروشگاه نیست")

    # Guard: gateway is active and configured
    if not gateway_config.is_active:
        raise PaymentConfigError("درگاه پرداخت غیرفعال است")
    if not gateway_config.is_configured:
        raise PaymentConfigError("پیکربندی درگاه ناقص است")

    # Idempotency: check for existing attempt
    if idempotency_key:
        existing = PaymentAttempt.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

    # Get adapter
    try:
        adapter = get_adapter(gateway_config.gateway_code)
    except KeyError as exc:
        raise PaymentConfigError(f"کد درگاه نامعتبر: {gateway_config.gateway_code}") from exc

    # Decrypt credentials
    try:
        credentials = gateway_config.get_credentials()
    except CredentialEncryptionError as exc:
        logger.error("Failed to decrypt credentials for config %d", gateway_config.pk)
        raise PaymentConfigError(
            "خطا در خواندن اعتبارنامه‌ی درگاه. لطفاً اعتبارنامه را دوباره وارد کنید."
        ) from exc

    # Create attempt record
    attempt = PaymentAttempt(
        store=store,
        order=order,
        gateway_config=gateway_config,
        amount=order.grand_total,
        currency="TOMAN",
        status=PaymentAttempt.Status.CREATED,
        idempotency_key=idempotency_key or "",
    )
    if pre_public_id:
        attempt.public_id = pre_public_id
    attempt.save()

    # For offline gateways (COD), mark as succeeded immediately
    if not adapter.is_online:
        attempt.status = PaymentAttempt.Status.SUCCEEDED
        attempt.gateway_track_id = f"cod-{order.code}"
        attempt.verified_at = timezone.now()
        attempt.save(update_fields=["status", "gateway_track_id", "verified_at", "updated_at"])
        # COD does NOT mark order as paid — it stays pending until delivery
        logger.info("COD payment recorded: order=%s attempt=%s", order.code, attempt.public_id)
        return attempt

    # Online gateway: request payment
    attempt.status = PaymentAttempt.Status.REQUESTING
    attempt.initiated_at = timezone.now()
    attempt.save(update_fields=["status", "initiated_at", "updated_at"])

    try:
        result = adapter.create_payment(
            amount=order.grand_total,
            currency="TOMAN",
            callback_url=callback_url,
            credentials=credentials,
            order_code=order.code,
            description=f"پرداخت سفارش {order.code}",
            sandbox=gateway_config.is_sandbox,
        )
    except GatewayError as exc:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_code = getattr(exc, "code", "gateway_error")
        attempt.failure_message = str(exc)[:300]
        attempt.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        logger.warning("Payment initiation failed: order=%s error=%s", order.code, exc)
        raise PaymentInitiationError(str(exc)) from exc

    # Store track_id and mark ready for redirect
    attempt.gateway_track_id = result.track_id
    attempt.status = PaymentAttempt.Status.REDIRECT_READY
    attempt.save(update_fields=["gateway_track_id", "status", "updated_at"])

    logger.info(
        "Payment initiated: order=%s attempt=%s trackId=%s",
        order.code, attempt.public_id, result.track_id,
    )
    return attempt


# ---------------------------------------------------------------------------
# Process callback and verify
# ---------------------------------------------------------------------------


def _sanitized_evidence(result) -> dict:
    """شواهدِ تأییدِ درگاه برایِ ذخیره — فقط فیلدهایِ امن (کارتِ ماسک‌شده، بدونِ اعتبارنامه/PII)."""
    return {
        "ref_id": str(getattr(result, "ref_id", ""))[:100],
        "card_number": str(getattr(result, "card_number", ""))[:25],
        "status_code": getattr(result, "status_code", 0),
        "message": str(getattr(result, "message", ""))[:200],
    }


def _open_reconciliation(*, attempt, order, kind, evidence, error="") -> PaymentReconciliation:
    """رکوردِ تطبیق (یکتا به‌ازای هر تلاش) + اعلانِ کارکنان. idempotent."""
    from apps.notifications.services.notification_service import sanitize_error

    error = sanitize_error(error)
    record, created = PaymentReconciliation.objects.get_or_create(
        attempt=attempt,
        defaults=dict(
            store=attempt.store, order=order, kind=kind, amount=attempt.amount,
            gateway_track_id=attempt.gateway_track_id, gateway_ref_id=attempt.gateway_ref_id,
            order_status_at_detection=order.status, payment_status_at_detection=order.payment_status,
            evidence=evidence, error_message=(error or "")[:300],
        ),
    )
    if created:
        logger.error(
            "Confirmed gateway payment NOT applied (%s): order=%s attempt=%s ref=%s amount=%s",
            kind, order.code, attempt.public_id, attempt.gateway_ref_id, attempt.amount,
        )
        from apps.notifications.services import business_events

        business_events.late_payment(record)
    return record


def _apply_verified_payment(attempt_pk: int, result, store) -> PaymentAttempt:
    """درگاه پول را تأیید کرده؛ سفارش را (اگر هنوز قابل‌پرداخت است) پرداخت‌شده می‌کند، وگرنه
    شواهد را در ``PaymentReconciliation`` نگه می‌دارد — هرگز بی‌صدا گم نمی‌شود.

    قفل: ابتدا ردیفِ **سفارش** و بعد تلاش (همان ترتیبِ ``change_order_status``/job انقضا) تا لغو و
    پرداختِ همزمان سریال شوند: یا لغو برنده است (⇒ تطبیق) یا پرداخت (⇒ لغوِ بعدی از PROCESSING)."""
    from apps.orders.services.lifecycle import apply_payment_success

    with transaction.atomic():
        pending = PaymentAttempt.objects.get(pk=attempt_pk)
        order = Order.objects.select_for_update().get(pk=pending.order_id)
        attempt = PaymentAttempt.objects.select_for_update().select_related("store").get(pk=attempt_pk)
        if attempt.status == PaymentAttempt.Status.SUCCEEDED:
            return attempt  # رقابتِ دو callback: دیگری پردازش کرده است

        attempt.status = PaymentAttempt.Status.SUCCEEDED
        attempt.gateway_ref_id = result.ref_id
        attempt.verified_at = timezone.now()
        attempt.failure_code = ""
        attempt.failure_message = ""
        attempt.save(update_fields=["status", "gateway_ref_id", "verified_at", "failure_code", "failure_message", "updated_at"])
        evidence = _sanitized_evidence(result)
        K = PaymentReconciliation.Kind

        if order.status == Order.Status.CANCELED:
            _open_reconciliation(attempt=attempt, order=order, kind=K.ORDER_CANCELED, evidence=evidence)
            return attempt
        if order.payment_status == Order.PaymentStatus.PAID:
            _open_reconciliation(attempt=attempt, order=order, kind=K.ALREADY_PAID, evidence=evidence)
            return attempt
        if order.payment_status != Order.PaymentStatus.PENDING:
            _open_reconciliation(attempt=attempt, order=order, kind=K.NOT_PAYABLE, evidence=evidence)
            return attempt

        try:
            with transaction.atomic():  # savepoint: خطا نباید شواهدِ پرداخت را با خود ببرد
                tx = apply_payment_success(
                    order, store=store, ref_id=result.ref_id, from_statuses=(Order.PaymentStatus.PENDING,),
                    note="پرداخت آنلاین موفق — سفارش به پردازش منتقل شد",
                )
        except Exception as exc:  # noqa: BLE001 — حفظِ شواهد مهم‌تر از نوعِ خطاست
            logger.exception("Applying verified payment failed: order=%s attempt=%s", order.code, attempt.public_id)
            _open_reconciliation(
                attempt=attempt, order=order, kind=K.PROCESSING_ERROR, evidence=evidence,
                error=f"{type(exc).__name__}: {exc}",
            )
            return attempt
        if tx is None:
            _open_reconciliation(attempt=attempt, order=order, kind=K.ALREADY_PAID, evidence=evidence)
            return attempt
    logger.info("Payment verified and order paid: order=%s attempt=%s ref=%s", order.code, attempt.public_id, result.ref_id)
    return attempt


def process_callback_and_verify(
    *,
    attempt_public_id: str,
    callback_data: dict,
    store,
) -> PaymentAttempt:
    """Process a gateway callback: verify with the gateway, then apply or reconcile.

    * ``SUCCEEDED`` attempt → idempotent return (duplicate callback).
    * Any other attempt — **including final ones** (failed/canceled/expired) — is verified with the
      gateway: money may have been taken (late callback, duplicate attempt, expired session).
    * Verified success on a payable order → order paid via ``apply_payment_success``.
    * Verified success on a canceled / already-paid / non-payable order (or if applying fails) →
      attempt recorded ``SUCCEEDED`` + persistent ``PaymentReconciliation``; the order is **not**
      reopened, marked paid or given its coupon back.
    * Verification failure on an open attempt → attempt ``FAILED`` (or ``CANCELED`` if the order was
      already paid) and ``PaymentVerificationFailed``; on an already-final attempt nothing changes.
    """
    attempt = (
        PaymentAttempt.objects
        .select_related("order", "gateway_config")
        .filter(public_id=attempt_public_id, store=store)
        .first()
    )
    if attempt is None:
        raise PaymentVerificationFailed("تلاش پرداخت یافت نشد")

    if attempt.status == PaymentAttempt.Status.SUCCEEDED:
        logger.info("Callback for already-succeeded attempt: %s", attempt.public_id)
        return attempt

    was_final = attempt.is_final
    order = attempt.order
    open_statuses = [s for s in PaymentAttempt.Status.values if s not in PaymentAttempt.FINAL_STATUSES]
    if not was_final:
        # گذارِ شرطی (نه ذخیره‌ی کورکورانه): callbackِ همزمانی که همین تلاش را SUCCEEDED کرده نباید پاک شود.
        PaymentAttempt.objects.filter(pk=attempt.pk, status__in=open_statuses).update(
            status=PaymentAttempt.Status.PENDING, updated_at=timezone.now(),
        )

    def fail(code: str, message: str, exc_message: str):
        if not was_final:  # یک تلاشِ نهایی‌شده با callbackِ تکراری/دیرهنگام بازنویسی نمی‌شود
            fresh_paid = Order.objects.filter(pk=order.pk, payment_status=Order.PaymentStatus.PAID).exists()
            PaymentAttempt.objects.filter(pk=attempt.pk, status__in=open_statuses).update(
                status=PaymentAttempt.Status.CANCELED if fresh_paid else PaymentAttempt.Status.FAILED,
                failure_code=code, failure_message=message[:300], updated_at=timezone.now(),
            )
        raise PaymentVerificationFailed(exc_message)

    if not attempt.gateway_track_id:
        fail("no_track_id", "شناسه‌ی پیگیریِ درگاه ثبت نشده", "تلاش پرداخت قابل‌تأیید نیست")

    gateway_config = attempt.gateway_config
    try:
        adapter = get_adapter(gateway_config.gateway_code)
        credentials = gateway_config.get_credentials()
    except (KeyError, CredentialEncryptionError) as exc:
        fail("config_error", "خطای پیکربندی درگاه", "خطای پیکربندی درگاه")
        raise exc  # unreachable — fail() always raises

    try:
        result = adapter.verify_payment(
            track_id=attempt.gateway_track_id,
            expected_amount=attempt.amount,
            currency=attempt.currency,
            credentials=credentials,
            callback_data=callback_data,
            sandbox=gateway_config.is_sandbox,
        )
    except GatewayError as exc:
        logger.warning("Verification failed: attempt=%s error=%s", attempt.public_id, exc)
        fail(getattr(exc, "code", "verify_error"), str(exc), str(exc))

    if not result.success:
        logger.info("Verification returned failure: attempt=%s final=%s", attempt.public_id, was_final)
        fail(f"status_{result.status_code}", result.message or "تأیید پرداخت ناموفق", result.message or "تأیید پرداخت توسط درگاه ناموفق بود")

    return _apply_verified_payment(attempt.pk, result, store)
