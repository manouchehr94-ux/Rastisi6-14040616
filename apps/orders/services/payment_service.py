"""لایه‌ی سرویس پرداخت — تشخیص بانک از BIN و شبیه‌سازی درگاه پرداخت.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶، قواعد ۱۰ و ۱۱.
"""

import random
import re

from django.db import transaction

from apps.notifications.services import business_events
from apps.orders.models import Order, Transaction
from apps.orders.services.coupon_redemption_service import mark_redeemed, release_redemption
from apps.orders.services.order_service import _order_sms_context, change_order_status
from apps.sms.events import SmsEvent
from apps.sms.services.sms_service import send_event_sms

TRANSACTION_CODE_PREFIX = "TX"

UNKNOWN_BANK_LABEL = "کارت بانکی نامشخص"

# نگاشت ۶ رقم اول شماره کارت (BIN) به نام بانک صادرکننده.
BANK_BINS = {
    "603799": "بانک ملی ایران",
    "610433": "بانک ملت",
    "627412": "بانک اقتصاد نوین",
    "627381": "بانک انصار",
    "621986": "بانک سامان",
    "627353": "بانک تجارت",
    "622106": "بانک پارسیان",
    "627884": "بانک پارسیان",
    "589210": "بانک سپه",
    "639347": "بانک پاسارگاد",
    "502229": "بانک پاسارگاد",
    "589463": "بانک رفاه کارگران",
    "627760": "پست بانک ایران",
    "628023": "بانک مسکن",
    "505785": "بانک ایران زمین",
    "636214": "بانک توسعه تعاون",
}


def detect_bank(card_number: str) -> str:
    """نام بانک صادرکننده را بر اساس ۶ رقم اول شماره‌ی کارت (BIN) برمی‌گرداند."""
    digits = re.sub(r"\D", "", card_number or "")
    if len(digits) < 6:
        return UNKNOWN_BANK_LABEL
    return BANK_BINS.get(digits[:6], UNKNOWN_BANK_LABEL)


def _generate_transaction_code() -> str:
    while True:
        code = f"{TRANSACTION_CODE_PREFIX}-{random.randint(10000, 99999)}"
        if not Transaction.objects.filter(code=code).exists():
            return code


def _generate_ref_id() -> str:
    return str(random.randint(100_000_000, 999_999_999))


@transaction.atomic
def simulate_payment(order: Order, success: bool, *, gateway=None, store) -> Transaction:
    """درگاه پرداخت شبیه‌سازی‌شده — بدون اتصال واقعی به بانک.

    در صورت موفقیت: تراکنش ok ثبت می‌شود، payment_status سفارش paid می‌شود
    و سفارش به وضعیت processing منتقل می‌شود (با ثبت در OrderStatusHistory).
    در صورت شکست: تراکنش fail ثبت می‌شود و payment_status سفارش failed می‌شود.

    ``store`` الزامی است — همان Store که برای پیامک‌های موفقیت/شکست پرداخت
    و برای ``change_order_status`` استفاده می‌شود.
    """
    if order.payment_status == Order.PaymentStatus.PAID:
        raise ValueError("این سفارش قبلاً پرداخت شده است")

    gateway = gateway or order.payment_gateway

    tx = Transaction.objects.create(
        code=_generate_transaction_code(),
        order=order,
        gateway=gateway,
        amount=order.grand_total,
        status=Transaction.Status.OK if success else Transaction.Status.FAIL,
        ref_id=_generate_ref_id() if success else "",
    )

    if success:
        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=["payment_status", "updated_at"])
        mark_redeemed(order)
        business_events.payment_result(order, success=True)
        change_order_status(
            order, Order.Status.PROCESSING, note="پرداخت موفق — سفارش به پردازش منتقل شد", store=store
        )
        transaction.on_commit(
            lambda: send_event_sms(
                SmsEvent.PAYMENT_SUCCESS, order.customer.phone, _order_sms_context(order), store=store
            )
        )
    else:
        order.payment_status = Order.PaymentStatus.FAILED
        order.save(update_fields=["payment_status", "updated_at"])
        release_redemption(order, reason="payment_failed")
        business_events.payment_result(order, success=False)
        transaction.on_commit(
            lambda: send_event_sms(
                SmsEvent.PAYMENT_FAILED, order.customer.phone, _order_sms_context(order), store=store
            )
        )

    return tx
