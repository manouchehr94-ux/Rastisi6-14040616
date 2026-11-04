"""تأییدِ دستیِ انتقالِ **کارت به کارت** (B3 / BLOCKER 3).

کارت به کارت مانندِ پرداخت در محل یک روشِ آفلاین است: مشتری خارج از سامانه وجه را
منتقل می‌کند و (در صورتِ تمایل) رسید می‌فرستد، اما این رسید هرگز به‌صورتِ خودکار
«پرداخت‌شده» را اثبات نمی‌کند. فقط یک مدیرِ مجاز (``order.confirm_cod_payment``)
می‌تواند دریافتِ واقعیِ وجه را تأیید کند.

این سرویس عیناً الگویِ ``cod_payment_service.confirm_collection`` را بازتاب می‌دهد:

* سفارش با ``select_for_update`` قفل می‌شود؛ سفارشِ لغوشده/پرداخت‌شده/غیرِ در‌انتظار رد می‌شود؛
* سفارش باید واقعاً «کارت به کارت» باشد (با ``gateway``/``PaymentGatewayConfig`` و اسکوپِ Store)؛
* مبلغ باید دقیقاً ``grand_total`` باشد؛
* از همان ``lifecycle.apply_payment_success`` استفاده می‌شود — UPDATE شرطی از ``pending``
  (دوبار تأیید ممکن نیست؛ تأییدِ تکراری ``AlreadyConfirmed`` می‌دهد و تراکنشِ دومی نمی‌سازد)،
  تراکنشِ OK با ``method``/``confirmed_by``، کدِ ``reserved → redeemed``، یک ایمیلِ رسید،
  **بدونِ پیامک**، و **بدونِ تغییرِ وضعیتِ سفارش**؛ سپس رویدادِ حسابرسی ثبت می‌شود؛
* مسیرِ «رد» تلاشِ پرداخت را FAILED/CANCELED می‌کند و سفارش را در ``pending`` و بدونِ جابه‌جاییِ
  پول نگه می‌دارد.

انتخابِ ``method``: ستونِ ``Transaction.Method`` دارایِ ``max_length=10`` است و افزودنِ یک
عضوِ ``'card_to_card'`` (۱۲ نویسه) نیازمندِ گشودنِ ستون با مهاجرت بود. چون تمایزِ معناییِ
جداگانه‌ای لازم نیست، از عضوِ موجودِ ``GATEWAY`` بازاستفاده می‌شود تا هیچ تغییرِ اسکیمایی
لازم نشود."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.core.services.audit_service import record_audit_event
from apps.orders.models import Order, PaymentAttempt, PaymentGatewayConfig, Transaction
from apps.orders.services.lifecycle import apply_payment_success

CARD_TO_CARD_CODE = "card_to_card"

#: تأییدِ کارت به کارت از عضوِ موجودِ ``GATEWAY`` استفاده می‌کند تا ستونِ
#: ``Transaction.Method`` (با ``max_length=10``) گشوده نشود و هیچ مهاجرتی لازم نباشد.
CONFIRMATION_METHOD = Transaction.Method.GATEWAY


class CardToCardConfirmationError(ValueError):
    """ورودی/وضعیتِ نامعتبر — پیام برایِ نمایش به مدیر مناسب است."""


class AlreadyConfirmed(CardToCardConfirmationError):
    """این سفارش قبلاً پرداخت‌شده است؛ تأییدِ تکراری هیچ اثری ندارد (idempotent)."""


def is_card_to_card_order(order: Order) -> bool:
    """سفارشِ کارت به کارت: درگاهِ سفارش کدِ ``card_to_card`` دارد یا با یک
    ``PaymentGatewayConfig`` آفلاینِ هم‌نام (اسکوپ‌شده به Storeِ سفارش) مطابقت دارد."""
    gateway = order.payment_gateway
    if gateway is None:
        return False
    if gateway.slug.lower() == CARD_TO_CARD_CODE:
        return True
    config = PaymentGatewayConfig.objects.filter(
        store_id=order.store_id, gateway_code=gateway.slug
    ).first()
    return (
        config is not None
        and not config.is_online
        and config.gateway_code == CARD_TO_CARD_CODE
    )


def can_confirm(order: Order) -> bool:
    """آیا فرمِ تأیید باید نمایش داده شود (کارت به کارت، پرداخت‌نشده، لغو‌نشده)."""
    return (
        order.status != Order.Status.CANCELED
        and order.payment_status == Order.PaymentStatus.PENDING
        and is_card_to_card_order(order)
    )


@transaction.atomic
def confirm_transfer(
    order_id: int, *, store, actor, amount, reference: str = "", idempotency_key: str = "",
) -> Transaction:
    """تأییدِ دستیِ دریافتِ انتقالِ کارت به کارت توسطِ مدیرِ مجاز.

    با قفلِ ردیفیِ سفارش و یک UPDATE شرطی از ``pending`` تضمین می‌کند تأیید فقط
    یک‌بار اعمال شود؛ تأییدِ همزمان/تکراری ``AlreadyConfirmed`` می‌دهد و تراکنشِ
    دومی (و بازخریدِ دوباره‌ی کد) ایجاد نمی‌شود."""
    order = (
        Order.objects.select_for_update()
        .select_related("payment_gateway", "customer")
        .get(pk=order_id, store=store)
    )
    if order.status == Order.Status.CANCELED:
        raise CardToCardConfirmationError("سفارشِ لغوشده قابلِ تأییدِ پرداخت نیست.")
    if order.payment_status == Order.PaymentStatus.PAID:
        raise AlreadyConfirmed("پرداختِ این سفارش قبلاً تأیید شده است.")
    if order.payment_status != Order.PaymentStatus.PENDING:
        raise CardToCardConfirmationError("وضعیتِ پرداختِ این سفارش اجازه‌ی تأیید نمی‌دهد.")
    if not is_card_to_card_order(order):
        raise CardToCardConfirmationError("این سفارش کارت به کارت نیست.")
    try:
        amount = Decimal(str(amount).replace(",", "").replace("٬", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise CardToCardConfirmationError("مبلغِ واردشده نامعتبر است.") from exc
    if amount != order.grand_total:
        raise CardToCardConfirmationError("مبلغِ دریافتی باید دقیقاً برابرِ مبلغِ کلِ سفارش باشد.")
    reference = (reference or "").strip()
    if len(reference) > 60:
        raise CardToCardConfirmationError("شماره‌ی رسید حداکثر ۶۰ نویسه است.")

    tx = apply_payment_success(
        order, store=store, ref_id=reference, note="تأییدِ دریافتِ انتقالِ کارت به کارت",
        from_statuses=(Order.PaymentStatus.PENDING,), gateway=order.payment_gateway,
        advance_to_processing=False, send_sms=False, method=CONFIRMATION_METHOD, confirmed_by=actor,
    )
    if tx is None:
        raise AlreadyConfirmed("پرداختِ این سفارش قبلاً تأیید شده است.")
    # Finalize the card-to-card attempt(s) in the SAME atomic block, using the
    # same terminal-success convention as the online engine
    # (``_apply_verified_payment``): SUCCEEDED + verified_at + gateway_ref_id,
    # failure fields cleared. Conditional UPDATE from PENDING only, scoped to
    # this order/store's card-to-card attempts: attempts that are already final
    # (or belong to another method) are left untouched, and a duplicate
    # confirmation never reaches here (AlreadyConfirmed above), so there is no
    # second transition.
    PaymentAttempt.objects.filter(
        order=order, store=store, status=PaymentAttempt.Status.PENDING,
        gateway_config__gateway_code=CARD_TO_CARD_CODE,
    ).update(
        status=PaymentAttempt.Status.SUCCEEDED,
        gateway_ref_id=(tx.ref_id or "")[:100],
        verified_at=tx.confirmed_at or timezone.now(),
        failure_code="", failure_message="",
        updated_at=timezone.now(),
    )
    record_audit_event(
        store=store, actor=actor, action_code="order.card_to_card_payment_confirmed",
        object_type="Order", object_id=order.pk, object_label=order.code,
        after={"amount": str(amount), "reference": reference, "transaction": tx.code},
        request_id=idempotency_key or f"card2card-{order.pk}",
    )
    return tx


@transaction.atomic
def reject_transfer(
    order_id: int, *, store, actor, reason: str = "", idempotency_key: str = "",
) -> None:
    """ردِ انتقالِ ادعاییِ کارت به کارت.

    تلاشِ پرداختِ در‌انتظار را CANCELED می‌کند و سفارش را در ``pending`` و بدونِ
    هیچ جابه‌جاییِ پول نگه می‌دارد. اگر سفارش قبلاً پرداخت شده باشد، رد رد می‌شود."""
    order = (
        Order.objects.select_for_update()
        .select_related("payment_gateway")
        .get(pk=order_id, store=store)
    )
    if order.payment_status == Order.PaymentStatus.PAID:
        raise CardToCardConfirmationError("سفارشِ پرداخت‌شده را نمی‌توان رد کرد.")
    if not is_card_to_card_order(order):
        raise CardToCardConfirmationError("این سفارش کارت به کارت نیست.")

    reason = (reason or "").strip()
    pending = PaymentAttempt.objects.select_for_update().filter(
        order=order, status=PaymentAttempt.Status.PENDING
    )
    for attempt in pending:
        # A PENDING card-to-card attempt must never carry verified_at (only
        # the merchant confirm path stamps it, and that also moves the attempt
        # out of PENDING). If one does, the evidence is inconsistent: refuse
        # explicitly (an ``assert`` would vanish under ``python -O``); the
        # surrounding atomic block rolls everything back.
        if attempt.verified_at is not None:
            raise CardToCardConfirmationError(
                "تلاشِ پرداختِ در انتظار دارای زمانِ تأیید است؛ رد کردن ممکن نیست و باید بررسیِ دستی شود."
            )
        attempt.status = PaymentAttempt.Status.CANCELED
        attempt.failure_code = "card_to_card_rejected"
        attempt.failure_message = (reason or "رسیدِ کارت به کارت توسطِ فروشنده رد شد.")[:300]
        attempt.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])

    # سفارش در ``pending`` می‌ماند؛ هیچ پولی ثبت نمی‌شود.
    record_audit_event(
        store=store, actor=actor, action_code="order.card_to_card_payment_rejected",
        object_type="Order", object_id=order.pk, object_label=order.code,
        after={"reason": reason},
        request_id=idempotency_key or f"card2card-reject-{order.pk}",
    )
