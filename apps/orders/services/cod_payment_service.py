"""تأییدِ دستیِ دریافتِ وجهِ **پرداخت در محل** (M3).

COD هرگز خودکار «پرداخت‌شده» نمی‌شود (تحویل، callback، import…). فقط یک مدیرِ مجاز
(Owner/Administrator/Order Manager — ``order.confirm_cod_payment``) می‌تواند دریافتِ واقعیِ وجه را تأیید کند:

* مبلغ باید دقیقاً ``grand_total`` باشد؛ روشِ دریافت (نقد/کارتخوان) و شماره‌ی رسید (اختیاری) ثبت می‌شود؛
* همان زیرساختِ موجود را به کار می‌برد: ``lifecycle.apply_payment_success`` — UPDATE شرطی از ``pending``
  (دوبار تأیید ممکن نیست)، تراکنشِ OK (تأییدکننده/زمان/روش)، کد ``reserved → redeemed``، یک ایمیلِ رسید
  (``payment.succeeded``؛ dedupe)، **بدونِ پیامک**، و **بدونِ تغییرِ وضعیتِ سفارش** (ارسال‌شده/تحویل‌شده حفظ می‌شود)؛
* اصلاحِ اشتباه فقط با روندِ استردادِ موجود (ردِ حسابرسی حفظ می‌شود)؛ «بازگرداندنِ تأیید» وجود ندارد."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core.services.audit_service import record_audit_event
from apps.orders.models import Order, PaymentGatewayConfig, Transaction
from apps.orders.services.lifecycle import apply_payment_success

COD_SLUG = "cod"
METHODS = (Transaction.Method.COD_CASH, Transaction.Method.COD_POS)


class CodConfirmationError(ValueError):
    """ورودی/وضعیتِ نامعتبر — پیام برایِ نمایش به مدیر مناسب است."""


class AlreadyConfirmed(CodConfirmationError):
    """این سفارش قبلاً پرداخت‌شده است؛ تأییدِ تکراری هیچ اثری ندارد (idempotent)."""


def is_cod_order(order: Order) -> bool:
    """سفارشِ پرداخت در محل: درگاهِ سفارش ``cod`` است یا با یک ``PaymentGatewayConfig`` آفلاین هم‌نام است."""
    gateway = order.payment_gateway
    if gateway is None:
        return False
    if gateway.slug.lower() == COD_SLUG:
        return True
    config = PaymentGatewayConfig.objects.filter(store_id=order.store_id, gateway_code=gateway.slug).first()
    return config is not None and not config.is_online


def can_confirm(order: Order) -> bool:
    """آیا فرمِ تأیید باید نمایش داده شود (COD، پرداخت‌نشده، لغو‌نشده)."""
    return (
        order.status != Order.Status.CANCELED
        and order.payment_status == Order.PaymentStatus.PENDING
        and is_cod_order(order)
    )


@transaction.atomic
def confirm_collection(
    order_id: int, *, store, actor, amount, method: str, reference: str = "", idempotency_key: str = "",
) -> Transaction:
    order = Order.objects.select_for_update().select_related("payment_gateway", "customer").get(pk=order_id, store=store)
    if order.status == Order.Status.CANCELED:
        raise CodConfirmationError("سفارشِ لغوشده قابلِ تأییدِ پرداخت نیست.")
    if order.payment_status == Order.PaymentStatus.PAID:
        raise AlreadyConfirmed("پرداختِ این سفارش قبلاً تأیید شده است.")
    if order.payment_status != Order.PaymentStatus.PENDING:
        raise CodConfirmationError("وضعیتِ پرداختِ این سفارش اجازه‌ی تأیید نمی‌دهد.")
    if not is_cod_order(order):
        raise CodConfirmationError("این سفارش پرداخت در محل نیست.")
    try:
        amount = Decimal(str(amount).replace(",", "").replace("٬", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise CodConfirmationError("مبلغِ واردشده نامعتبر است.") from exc
    if amount != order.grand_total:
        raise CodConfirmationError("مبلغِ دریافتی باید دقیقاً برابرِ مبلغِ کلِ سفارش باشد.")
    if method not in METHODS:
        raise CodConfirmationError("روشِ دریافت نامعتبر است.")
    reference = (reference or "").strip()
    if len(reference) > 60:
        raise CodConfirmationError("شماره‌ی رسید حداکثر ۶۰ نویسه است.")

    tx = apply_payment_success(
        order, store=store, ref_id=reference, note="تأییدِ دریافتِ وجهِ پرداخت در محل",
        from_statuses=(Order.PaymentStatus.PENDING,), gateway=order.payment_gateway,
        advance_to_processing=False, send_sms=False, method=method, confirmed_by=actor,
    )
    if tx is None:
        raise AlreadyConfirmed("پرداختِ این سفارش قبلاً تأیید شده است.")
    record_audit_event(
        store=store, actor=actor, action_code="order.cod_payment_confirmed",
        object_type="Order", object_id=order.pk, object_label=order.code,
        after={"amount": str(amount), "method": method, "reference": reference, "transaction": tx.code},
        request_id=idempotency_key or f"cod-{order.pk}",
    )
    return tx
