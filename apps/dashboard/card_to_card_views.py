"""تأییدِ/ردِ دستیِ انتقالِ کارت به کارت از صفحه‌ی سفارش — فقط Owner/Administrator/Order Manager.

کارت به کارت عیناً مانندِ پرداخت در محل یک روشِ آفلاین است و همان مجوزِ
``order.confirm_cod_payment`` (Owner/Administrator/Order Manager) و همان اسکوپِ Store و
الگویِ idempotency را به کار می‌برد. تفاوتِ ساختاری فقط این است که کارت به کارت علاوه بر
«تأیید» یک مسیرِ «رد» هم دارد (رسیدِ نامعتبر)، که سفارش را در ``pending`` و بدونِ جابه‌جاییِ
پول نگه می‌دارد تا مشتری دوباره تلاش کند یا سفارش منقضی شود."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.orders.services import card_to_card_payment_service as c2c
from apps.stores.authorization import ORDER_CONFIRM_COD_PAYMENT, ORDER_VIEW

from .decorators import permission_required, staff_required


@require_POST
@staff_required
@permission_required(ORDER_VIEW)
@permission_required(ORDER_CONFIRM_COD_PAYMENT)
def order_confirm_card_to_card_payment(request, code):
    order = get_object_or_404(Order, code=code, store=request.store)
    try:
        c2c.confirm_transfer(
            order.pk, store=request.store, actor=request.user,
            amount=request.POST.get("amount", ""),
            reference=request.POST.get("reference", ""),
            idempotency_key=request.POST.get("token", "")[:64],
        )
    except c2c.AlreadyConfirmed as exc:
        messages.info(request, str(exc))
    except c2c.CardToCardConfirmationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "دریافتِ انتقالِ کارت به کارت تأیید شد و رسیدِ پرداخت ثبت گردید.")
    return redirect("dashboard:order-detail", code=order.code)


@require_POST
@staff_required
@permission_required(ORDER_VIEW)
@permission_required(ORDER_CONFIRM_COD_PAYMENT)
def order_reject_card_to_card_payment(request, code):
    order = get_object_or_404(Order, code=code, store=request.store)
    try:
        c2c.reject_transfer(
            order.pk, store=request.store, actor=request.user,
            reason=request.POST.get("reason", ""),
            idempotency_key=request.POST.get("token", "")[:64],
        )
    except c2c.CardToCardConfirmationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "انتقالِ کارت به کارت رد شد؛ سفارش در انتظارِ پرداخت باقی ماند.")
    return redirect("dashboard:order-detail", code=order.code)
