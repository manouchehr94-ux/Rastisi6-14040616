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
from apps.orders.models import Order, PaymentAttempt, PaymentGatewayConfig, Transaction

logger = logging.getLogger("payment")

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PaymentServiceError(Exception):
    """Base for payment service errors — safe message for logs/admin."""


class PaymentAlreadyPaidError(PaymentServiceError):
    """Order is already paid."""


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
    # Guard: already paid
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


def process_callback_and_verify(
    *,
    attempt_public_id: str,
    callback_data: dict,
    store,
) -> PaymentAttempt:
    """Process a gateway callback: lock attempt, verify with gateway, update states.

    This is the authoritative payment confirmation path. It:
    1. Locks the PaymentAttempt row (select_for_update)
    2. Checks for already-processed (idempotent)
    3. Calls gateway verify_payment
    4. On success: marks attempt SUCCEEDED, order PAID, triggers transition
    5. On failure: marks attempt FAILED with reason

    Args:
        attempt_public_id: The PaymentAttempt's public_id.
        callback_data: Query params or POST data from the callback.
        store: Authoritative store.

    Returns:
        Updated PaymentAttempt.

    Raises:
        PaymentVerificationFailed: If verification fails (order NOT paid).
    """
    # Pre-check: attempt exists (outside atomic to allow raising without rollback)
    attempt = (
        PaymentAttempt.objects
        .select_related("order", "gateway_config")
        .filter(public_id=attempt_public_id, store=store)
        .first()
    )

    if attempt is None:
        raise PaymentVerificationFailed("تلاش پرداخت یافت نشد")

    # Already processed — idempotent return
    if attempt.is_final:
        logger.info(
            "Callback for already-final attempt: %s status=%s",
            attempt.public_id, attempt.status,
        )
        return attempt

    order = attempt.order

    # Already paid by another attempt — mark this one as canceled
    if order.payment_status == Order.PaymentStatus.PAID:
        attempt.status = PaymentAttempt.Status.CANCELED
        attempt.failure_message = "سفارش قبلاً توسط تلاش دیگری پرداخت شده"
        attempt.save(update_fields=["status", "failure_message", "updated_at"])
        return attempt

    # Mark as pending verification
    attempt.status = PaymentAttempt.Status.PENDING
    attempt.save(update_fields=["status", "updated_at"])

    # Get adapter and credentials
    gateway_config = attempt.gateway_config
    try:
        adapter = get_adapter(gateway_config.gateway_code)
        credentials = gateway_config.get_credentials()
    except (KeyError, CredentialEncryptionError) as exc:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_code = "config_error"
        attempt.failure_message = "خطای پیکربندی درگاه"
        attempt.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        logger.error("Config error during verification: %s", exc)
        raise PaymentVerificationFailed("خطای پیکربندی درگاه") from exc

    # Server-to-server verification
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
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_code = getattr(exc, "code", "verify_error")
        attempt.failure_message = str(exc)[:300]
        attempt.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        logger.warning("Verification failed: attempt=%s error=%s", attempt.public_id, exc)
        raise PaymentVerificationFailed(str(exc)) from exc

    if not result.success:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_code = f"status_{result.status_code}"
        attempt.failure_message = result.message[:300] if result.message else "تأیید پرداخت ناموفق"
        attempt.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        logger.info("Verification returned failure: attempt=%s", attempt.public_id)
        raise PaymentVerificationFailed(
            result.message or "تأیید پرداخت توسط درگاه ناموفق بود"
        )

    # SUCCESS — use atomic block for the critical order-paid transition
    with transaction.atomic():
        # Re-lock the attempt inside the atomic block
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)

        # Double-check not already final (concurrent callback race)
        if attempt.is_final:
            return attempt

        attempt.status = PaymentAttempt.Status.SUCCEEDED
        attempt.gateway_ref_id = result.ref_id
        attempt.verified_at = timezone.now()
        attempt.save(update_fields=["status", "gateway_ref_id", "verified_at", "updated_at"])

        # گذارِ «پرداخت‌شده» + همه‌ی اثرهای جانبی (مصرف کد، اعلان، hook کمپین، تراکنشِ سازگاری،
        # PROCESSING، پیامک) یک‌جا در lifecycle؛ فقط از PENDING (UPDATE شرطی برایِ امنیتِ رقابت).
        from apps.orders.services.lifecycle import apply_payment_success

        tx = apply_payment_success(
            order, store=store, ref_id=result.ref_id, from_statuses=(Order.PaymentStatus.PENDING,),
            note="پرداخت آنلاین موفق — سفارش به پردازش منتقل شد",
        )
        if tx is None:
            # Order was already paid by a concurrent request
            logger.warning(
                "Order already paid when attempt succeeded: order=%s attempt=%s",
                order.code, attempt.public_id,
            )
            return attempt

    logger.info(
        "Payment verified and order paid: order=%s attempt=%s ref=%s",
        order.code, attempt.public_id, result.ref_id,
    )
    return attempt
