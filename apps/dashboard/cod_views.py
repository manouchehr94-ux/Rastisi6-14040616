"""تأییدِ دریافتِ وجهِ پرداخت در محل از صفحه‌ی سفارش — فقط Owner/Administrator/Order Manager."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.orders.services import cod_payment_service
from apps.stores.authorization import ORDER_CONFIRM_COD_PAYMENT, ORDER_VIEW

from .decorators import permission_required, staff_required


@require_POST
@staff_required
@permission_required(ORDER_VIEW)
@permission_required(ORDER_CONFIRM_COD_PAYMENT)
def order_confirm_cod_payment(request, code):
    order = get_object_or_404(Order, code=code, store=request.store)
    try:
        cod_payment_service.confirm_collection(
            order.pk, store=request.store, actor=request.user, amount=request.POST.get("amount", ""),
            method=request.POST.get("method", ""), reference=request.POST.get("reference", ""),
            idempotency_key=request.POST.get("token", "")[:64],
        )
    except cod_payment_service.AlreadyConfirmed as exc:
        messages.info(request, str(exc))
    except cod_payment_service.CodConfirmationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "دریافتِ وجه تأیید شد و رسیدِ پرداخت ثبت گردید.")
    return redirect("dashboard:order-detail", code=order.code)
