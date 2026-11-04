"""صفِ بررسیِ پرداختِ کارت‌به‌کارت — فقط مدیرِ دارای مجوزِ ``order.review_card_transfer`` (Owner/Administrator/Order Manager).

هر تصمیم از ``card_transfer_service`` می‌گذرد (قفل، اتمیک، idempotent، حسابرسی) و Store-scoped است؛ تأیید همان مسیرِ
``lifecycle.apply_payment_success`` را اجرا می‌کند و مسیرِ موازی ندارد."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.orders.models import CardTransferSubmission, Order
from apps.orders.services import card_transfer_service as svc
from apps.stores.authorization import ORDER_REVIEW_CARD_TRANSFER, ORDER_VIEW

from .decorators import permission_required, staff_required

S = CardTransferSubmission.Status
FILTERS = (("submitted", "در انتظار بررسی"), ("approved", "تأییدشده"), ("rejected", "ردشده"), ("all", "همه"))


@staff_required
@permission_required(ORDER_VIEW)
@permission_required(ORDER_REVIEW_CARD_TRANSFER)
def card_transfer_list(request):
    store = request.store
    status = request.GET.get("status", "submitted")
    status = status if status in dict(FILTERS) else "submitted"
    qs = CardTransferSubmission.objects.filter(store=store).select_related("order", "order__customer", "reviewed_by", "transaction")
    if status != "all":
        qs = qs.filter(status=status)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    rows = list(page)
    for row in rows:
        row.is_canceled = row.order.status == Order.Status.CANCELED
        row.duplicate_tracking = row.status == S.SUBMITTED and svc.tracking_seen_elsewhere(row)
    open_stats = CardTransferSubmission.objects.filter(store=store, status=S.SUBMITTED).aggregate(n=Count("pk"), total=Sum("amount"))
    return render(request, "dashboard/card_transfers.html", {
        "page": page, "rows": rows, "status": status, "filters": FILTERS, "active_page": "card-transfers",
        "open_count": open_stats["n"] or 0, "open_total": open_stats["total"] or 0,
        "approved_count": CardTransferSubmission.objects.filter(store=store, status=S.APPROVED).count(),
        "rejected_count": CardTransferSubmission.objects.filter(store=store, status=S.REJECTED).count(),
    })


@require_POST
@staff_required
@permission_required(ORDER_VIEW)
@permission_required(ORDER_REVIEW_CARD_TRANSFER)
def card_transfer_decide(request, pk, action):
    store = request.store
    submission = get_object_or_404(CardTransferSubmission, pk=pk, store=store)
    nxt = request.POST.get("next", "")
    target = nxt if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}) and nxt.startswith("/") else None
    try:
        if action == "approve":
            svc.approve(submission.pk, store=store, actor=request.user, allow_duplicate_tracking=request.POST.get("allow_duplicate") == "1")
            messages.success(request, f"پرداختِ سفارش {submission.order.code} تأیید شد و سفارش پرداخت‌شده ثبت گردید.")
        elif action == "reject":
            svc.reject(submission.pk, store=store, actor=request.user, reason=request.POST.get("reason", ""))
            messages.info(request, f"پرداختِ سفارش {submission.order.code} رد شد؛ مشتری می‌تواند اطلاعاتِ درست را دوباره ثبت کند.")
        else:
            return redirect("dashboard:card-transfer-list")
    except svc.AlreadyDecided as exc:
        messages.info(request, str(exc))
    except svc.CardTransferError as exc:
        messages.error(request, str(exc))
    return redirect(target or "dashboard:card-transfer-list")
