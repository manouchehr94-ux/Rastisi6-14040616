"""تعریف‌هایِ مشترکِ «سفارشِ معتبرِ مشتری» (G1).

یک‌جا تعریف می‌شود که برایِ آمارِ مشتری (تعداد سفارش، مجموعِ خرید، دورهٔ خرید) چه
سفارشی «معتبر» است و استردادِ «فعال» چیست. مصرف‌کنندگان:

* موتورِ قواعدِ کمپین (``apps.engagement.services.rule_data``) — همیشه «معتبر»؛
* موتورِ سگمنت (``apps.dashboard.services.segment_service``) — تعریفِ ``LEGACY`` (رفتارِ
  تاریخیِ سگمنت‌ها، تغییرناپذیر تا تأییدِ مالک) یا ``VALID`` (این تعریفِ مشترک).

سگمنتِ کش‌شده (عضویتِ ذخیره‌شده، برایِ UI/بازاریابیِ ایستا) و ارزیابیِ زندهٔ کمپین
عمداً دو لایهٔ جدا می‌مانند؛ فقط **تعاریفِ پایه** مشترک است."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from apps.orders.models import Order, Refund

#: وضعیتِ پرداختِ پیش‌فرضِ «سفارشِ معتبر» (کمپین می‌تواند فهرستِ دیگری بدهد).
DEFAULT_VALID_PAYMENT_STATUSES = (Order.PaymentStatus.PAID,)


def valid_order_q(valid_statuses=DEFAULT_VALID_PAYMENT_STATUSES, *, prefix: str = "") -> Q:
    """سفارشِ معتبر: وضعیتِ پرداختِ مجاز و لغو‌نشده. ``prefix`` برایِ استفاده از رویِ Customer (``"orders__"``)."""
    return Q(**{f"{prefix}payment_status__in": list(valid_statuses)}) & ~Q(**{f"{prefix}status": Order.Status.CANCELED})


def valid_orders(store, valid_statuses=DEFAULT_VALID_PAYMENT_STATUSES, start=None, end=None):
    """سفارش‌هایِ معتبرِ همین Store؛ بازه‌ی نیم‌باز ``[start, end)``."""
    qs = Order.objects.filter(store=store).filter(valid_order_q(valid_statuses))
    if start is not None:
        qs = qs.filter(created_at__gte=start)
    if end is not None:
        qs = qs.filter(created_at__lt=end)
    return qs


def active_refunds(qs):
    """استردادِ فعال = همه به‌جز ناموفق/لغوشده."""
    return qs.exclude(status__in=Refund.INACTIVE_STATUSES)


def refunded_amount_subquery(order_ref):
    """جمعِ استردادهایِ فعالِ یک سفارش (برایِ ``Subquery``)؛ ``order_ref`` معمولاً ``OuterRef("pk")``."""
    return (
        active_refunds(Refund.objects.filter(order=order_ref))
        .values("order").annotate(total=Sum(Coalesce("approved_amount", "requested_amount"))).values("total")
    )


def net_amount(grand_total: Decimal, refunded: Decimal) -> Decimal:
    return max(Decimal("0"), grand_total - (refunded or Decimal("0")))


@dataclass(frozen=True)
class CustomerOrderDefinition:
    """کدام سفارش‌ها در آمارِ مشتریِ سگمنت شمرده می‌شوند. هر فیلد یک ``Q`` روی رابطه‌ی ``orders__``."""
    key: str
    count_q: Q       # order_count
    spent_q: Q       # total_spent
    activity_q: Q    # first/last order، no_purchase_for_days، خریدِ کالا/دسته، استفاده از کد


#: رفتارِ تاریخیِ موتورِ سگمنت: همه‌ی سفارش‌ها (حتی لغو/پرداخت‌نشده) در تعداد/تاریخ/کالا/کد؛
#: «مجموعِ خرید» فقط سفارش‌هایِ ``paid`` (حتی اگر بعداً لغو شده باشند).
LEGACY = CustomerOrderDefinition(
    "legacy", count_q=Q(), spent_q=Q(orders__payment_status=Order.PaymentStatus.PAID), activity_q=Q(),
)
#: تعریفِ مشترک با موتورِ قواعد: فقط سفارشِ معتبر در همه‌ی معیارها.
VALID = CustomerOrderDefinition(
    "valid", count_q=valid_order_q(prefix="orders__"), spent_q=valid_order_q(prefix="orders__"),
    activity_q=valid_order_q(prefix="orders__"),
)
DEFINITIONS = {d.key: d for d in (LEGACY, VALID)}
