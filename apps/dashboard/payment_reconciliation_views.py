"""تطبیقِ پرداخت‌ها: پرداخت‌هایی که درگاه تأیید کرده اما سفارش نپذیرفته (لغوشده/تکراری/خطا).

فقط‌نمایش + علامت‌گذاریِ رسیدگی؛ این صفحه هرگز سفارش را بازگشایی/پرداخت‌شده نمی‌کند و پولی
جابه‌جا نمی‌کند (استردادِ واقعی خارج از سیستم/با روندِ استردادِ موجود انجام می‌شود)."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.services.audit_service import record_audit_event
from apps.orders.models import PaymentReconciliation
from apps.stores.authorization import REFUND_MANAGE, REFUND_VIEW, membership_has_permission

from .decorators import permission_required, staff_required


@staff_required
@permission_required(REFUND_VIEW, REFUND_MANAGE)
def payment_reconciliation_list(request):
    qs = PaymentReconciliation.objects.filter(store=request.store).select_related("order", "attempt", "resolved_by")
    status = request.GET.get("status", "open")
    if status in PaymentReconciliation.Status.values:
        qs = qs.filter(status=status)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "dashboard/payment_reconciliations.html", {
        "page": page, "status": status, "active_page": "payment-reconciliations",
        "resolutions": PaymentReconciliation.Resolution.choices,
        "can_resolve": membership_has_permission(request.store_membership, REFUND_MANAGE),
        "open_count": PaymentReconciliation.objects.filter(store=request.store, status="open").count(),
    })


@require_POST
@staff_required
@permission_required(REFUND_MANAGE)
def payment_reconciliation_resolve(request, pk):
    record = get_object_or_404(PaymentReconciliation, pk=pk, store=request.store)
    resolution = request.POST.get("resolution", "")
    note = request.POST.get("note", "").strip()[:500]
    if resolution not in PaymentReconciliation.Resolution.values:
        messages.error(request, "نتیجه‌ی رسیدگی نامعتبر است.")
    elif record.status == PaymentReconciliation.Status.RESOLVED:
        messages.info(request, "این مورد قبلاً رسیدگی شده است.")
    else:
        updated = PaymentReconciliation.objects.filter(pk=record.pk, status=PaymentReconciliation.Status.OPEN).update(
            status=PaymentReconciliation.Status.RESOLVED, resolution=resolution, resolution_note=note,
            resolved_by=request.user, resolved_at=timezone.now(),
        )
        if updated:
            record_audit_event(
                store=request.store, actor=request.user, action_code="payment_reconciliation.resolved",
                object_type="PaymentReconciliation", object_id=record.pk, object_label=record.order.code,
                after={"resolution": resolution, "amount": str(record.amount)}, request_id=f"reconcile-{record.pk}",
            )
            messages.success(request, "رسیدگی ثبت شد.")
    return redirect(request.POST.get("next") or "dashboard:payment-reconciliations")
