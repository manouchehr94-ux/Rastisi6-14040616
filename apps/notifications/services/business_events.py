"""نقاطِ اتصالِ رویدادهایِ کسب‌وکار به سیستمِ اعلان. هر تابع اعلان را از
طریقِ ``safe_dispatch`` در همان تراکنشِ کسب‌وکار صف می‌کند (Outbox) و هرگز
استثنا پرتاب نمی‌کند."""

from __future__ import annotations

from apps.notifications.services import context_builders as cb
from apps.notifications.services.dispatcher import safe_dispatch

_STATUS_EVENTS = {
    "processing": "order.processing",
    "shipped": "order.shipped",
    "delivered": "order.delivered",
    "canceled": "order.canceled",
}


def order_created(order) -> None:
    store = order.store
    ctx = cb.order_context(store, order)
    safe_dispatch("order.created", store=store, customer=order.customer, order=order, context=ctx,
                  dedupe_key=f"order:{order.pk}")
    gift = order.items.filter(gift_wrap_selected=True).exists()
    safe_dispatch(
        "staff.order_created", store=store, order=order, dedupe_key=f"order:{order.pk}",
        context={**ctx, "gift_wrap_note": "🎁 این سفارش شاملِ کادوپیچی است." if gift else ""},
    )


def order_status_changed(order, to_status: str) -> None:
    event = _STATUS_EVENTS.get(to_status)
    if event:
        safe_dispatch(event, store=order.store, customer=order.customer, order=order,
                      context=cb.order_context(order.store, order), dedupe_key=f"order:{order.pk}:{to_status}")


def payment_result(order, *, success: bool) -> None:
    ctx = cb.order_context(order.store, order)
    if success:
        safe_dispatch("payment.succeeded", store=order.store, customer=order.customer, order=order, context=ctx,
                      dedupe_key=f"order:{order.pk}")
    else:
        attempts = order.transactions.count() if hasattr(order, "transactions") else 0
        safe_dispatch("payment.failed", store=order.store, customer=order.customer, order=order, context=ctx,
                      dedupe_key=f"order:{order.pk}:{attempts}")


def coupon_redeemed(order, coupon, discount_amount) -> None:
    ctx = {
        **cb.order_context(order.store, order), "discount_code": coupon.code,
        "discount_amount": cb.discount_amount_label(coupon),
    }
    safe_dispatch("coupon.redeemed", store=order.store, customer=order.customer, order=order, context=ctx,
                  dedupe_key=f"order:{order.pk}")


def return_event(return_request, kind: str, *, reason: str = "") -> None:
    """``kind``: requested | approved | rejected"""
    order = return_request.order
    store = return_request.store
    ctx = {**cb.order_context(store, order), "return_number": return_request.return_number, "reason": reason}
    safe_dispatch(f"return.{kind}", store=store, customer=return_request.customer, order=order, context=ctx,
                  dedupe_key=f"return:{return_request.pk}")
    if kind == "requested":
        safe_dispatch("staff.return_requested", store=store, order=order, context=ctx,
                      dedupe_key=f"return:{return_request.pk}")


def refund_completed(refund) -> None:
    from apps.core.utils import format_toman

    order = refund.order
    ctx = {**cb.order_context(refund.store, order), "refund_amount": format_toman(refund.approved_amount, with_unit=False)}
    safe_dispatch("refund.completed", store=refund.store, customer=order.customer, order=order, context=ctx,
                  dedupe_key=f"refund:{refund.pk}")


def account_registered(customer, store) -> None:
    safe_dispatch("account.registered", store=store, customer=customer, context=cb.customer_context(store, customer),
                  dedupe_key=f"customer:{customer.pk}")


def account_sensitive_changed(customer, store, changed_field: str) -> None:
    from django.utils import timezone

    safe_dispatch(
        "account.sensitive_changed", store=store, customer=customer,
        context={**cb.customer_context(store, customer), "changed_field": changed_field},
        dedupe_key=f"customer:{customer.pk}:{changed_field}:{timezone.now():%Y%m%d%H%M}",
    )


def review_created(review, store) -> None:
    safe_dispatch(
        "staff.review_created", store=store, customer=review.customer,
        context={"product_title": review.product.name, "rating": str(review.rating),
                 "customer_name": review.customer.full_name, "store_name": store.name},
        dedupe_key=f"review:{review.pk}",
    )


def late_payment(record, *, upgraded: bool = False) -> None:
    """مغایرت/پرداختِ اعمال‌نشده (``PaymentReconciliation``) → ایمیل به کارکنانِ مالی؛ یک‌بار به‌ازای هر رکورد
    (و یک‌بار دیگر اگر مورد «مشکوک» به «تأییدشده» ارتقا یابد)."""
    from apps.core.utils import format_toman
    from apps.orders.models import PaymentReconciliation as PR

    order = record.order
    reason = f"{record.get_evidence_level_display()} — {record.get_kind_display()}"
    if record.reported_amount is not None and record.kind == PR.Kind.AMOUNT_MISMATCH:
        reason += f" (مبلغِ گزارش‌شده‌ی درگاه: {format_toman(record.reported_amount, with_unit=False)} تومان)"
    ctx = {
        **cb.order_context(record.store, order),
        "order_total": format_toman(record.amount, with_unit=False),
        "reconciliation_reason": reason,
    }
    key = f"reconcile:{record.pk}" + (":confirmed" if upgraded else "")
    safe_dispatch("staff.late_payment", store=record.store, order=order, context=ctx, dedupe_key=key)
