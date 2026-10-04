"""درخواستِ مرجوعی — گردشِ وضعیتِ صریح، اعتبارسنجیِ تعداد، و یکپارچگی با
دفتر موجودی و استرداد (ADR-34).

هیچ ویویی نباید مستقیماً ``ReturnRequest.status`` را تغییر دهد — همیشه از
طریق یکی از توابع این ماژول، که گذارِ مجاز را بررسی، رکوردهای مرتبط را
قفل، و رخدادِ حسابرسی ثبت می‌کنند.
"""

import random
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.services.inventory_service import (
    ReturnItemAlreadyRestockedError,
    restock_return_item,
)
from apps.core.services.audit_service import record_audit_event
from apps.notifications.services import business_events
from apps.orders.models import OrderItem, Refund, ReturnItem, ReturnRequest

RETURN_NUMBER_PREFIX = "RET"


class ReturnError(Exception):
    """خطای قابل‌نمایش هنگام مدیریتِ درخواستِ مرجوعی."""


def _generate_return_number(store) -> str:
    while True:
        code = f"{RETURN_NUMBER_PREFIX}-{random.randint(10000, 99999)}"
        if not ReturnRequest.objects.filter(store=store, return_number=code).exists():
            return code


def _reserved_return_quantity(order_item: OrderItem) -> int:
    """مجموعِ تعدادی که در درخواست‌های مرجوعیِ غیرِ رد/لغوشده برای این قلم
    رزرو شده — یک قلمِ سفارش می‌تواند چند درخواستِ مرجوعیِ جداگانه داشته
    باشد، اما مجموعِ آن‌ها هرگز نباید از تعدادِ خریداری‌شده بیشتر شود."""
    total = 0
    for item in ReturnItem.objects.filter(order_item=order_item).exclude(
        return_request__status__in=(ReturnRequest.Status.REJECTED, ReturnRequest.Status.CANCELLED)
    ):
        total += item.quantity_requested
    return total


@transaction.atomic
def create_return_request(
    order, *, store, customer, reason, line_requests: list[dict], customer_explanation: str = "", actor=None,
) -> ReturnRequest:
    """``line_requests``: فهرستی از ``{"order_item_id": int, "quantity": int}``."""
    if order.store_id != store.pk:
        raise ReturnError("این سفارش متعلق به این فروشگاه نیست.")
    if order.customer_id != customer.pk:
        raise ReturnError("این سفارش متعلق به این مشتری نیست.")
    if not line_requests:
        raise ReturnError("حداقل یک قلم برای مرجوعی لازم است.")

    return_request = ReturnRequest.objects.create(
        store=store, order=order, customer=customer, return_number=_generate_return_number(store),
        reason=reason, customer_explanation=customer_explanation, actor=actor,
    )
    for entry in line_requests:
        order_item = OrderItem.objects.filter(pk=entry["order_item_id"], order=order).first()
        if order_item is None:
            raise ReturnError("این قلمِ سفارش متعلق به این سفارش نیست.")
        quantity = int(entry["quantity"])
        available = order_item.quantity - _reserved_return_quantity(order_item)
        if quantity <= 0 or quantity > available:
            raise ReturnError(
                f"برای «{order_item.product_name}» حداکثر {max(available, 0)} عدد قابل‌درخواست است."
            )
        ReturnItem.objects.create(return_request=return_request, order_item=order_item, quantity_requested=quantity)

    record_audit_event(
        store=store, actor=actor, action_code="return.created",
        object_type="ReturnRequest", object_id=return_request.pk, object_label=return_request.return_number,
        after={"reason": reason, "item_count": len(line_requests)},
    )
    business_events.return_event(return_request, "requested")
    return return_request


def _transition(return_request: ReturnRequest, to_status: str, *, store, actor=None):
    if return_request.store_id != store.pk:
        raise ReturnError("این درخواستِ مرجوعی متعلق به این فروشگاه نیست.")
    from_status = return_request.status
    if from_status in ReturnRequest.FINAL_STATUSES:
        raise ReturnError(f"درخواستِ مرجوعی در وضعیتِ نهاییِ «{return_request.get_status_display()}» است.")
    if to_status not in ReturnRequest.ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ReturnError(f"گذار از «{from_status}» به «{to_status}» مجاز نیست.")
    return_request.status = to_status
    return_request.actor = actor
    return from_status


@transaction.atomic
def review_return_request(return_request: ReturnRequest, *, store, actor=None) -> ReturnRequest:
    _transition(return_request, ReturnRequest.Status.UNDER_REVIEW, store=store, actor=actor)
    return_request.save(update_fields=["status", "actor", "updated_at"])
    return return_request


@transaction.atomic
def approve_return_request(
    return_request: ReturnRequest, *, store, actor=None, approved_quantities: dict | None = None, note: str = "",
) -> ReturnRequest:
    _transition(return_request, ReturnRequest.Status.APPROVED, store=store, actor=actor)
    approved_quantities = approved_quantities or {}

    for item in return_request.items.select_for_update():
        requested = approved_quantities.get(item.pk, item.quantity_requested)
        requested = int(requested)
        if requested < 0 or requested > item.quantity_requested:
            raise ReturnError(f"تعدادِ تأییدشده برای «{item.order_item.product_name}» نامعتبر است.")
        item.quantity_approved = requested
        item.save(update_fields=["quantity_approved", "updated_at"])

    return_request.approved_at = timezone.now()
    if note:
        return_request.merchant_note = note
    return_request.save(update_fields=["status", "actor", "approved_at", "merchant_note", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="return.approved",
        object_type="ReturnRequest", object_id=return_request.pk, object_label=return_request.return_number,
    )
    business_events.return_event(return_request, "approved")
    return return_request


@transaction.atomic
def reject_return_request(return_request: ReturnRequest, *, store, actor=None, rejection_reason: str) -> ReturnRequest:
    if not rejection_reason.strip():
        raise ReturnError("علتِ ردِ مرجوعی الزامی است.")
    _transition(return_request, ReturnRequest.Status.REJECTED, store=store, actor=actor)
    return_request.rejected_at = timezone.now()
    return_request.merchant_note = rejection_reason
    return_request.save(update_fields=["status", "actor", "rejected_at", "merchant_note", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="return.rejected",
        object_type="ReturnRequest", object_id=return_request.pk, object_label=return_request.return_number,
        after={"reason": rejection_reason},
    )
    business_events.return_event(return_request, "rejected", reason=rejection_reason)
    return return_request


@transaction.atomic
def mark_return_received(
    return_request: ReturnRequest, *, store, actor=None, received_quantities: dict | None = None,
) -> ReturnRequest:
    _transition(return_request, ReturnRequest.Status.RECEIVED, store=store, actor=actor)
    received_quantities = received_quantities or {}

    for item in return_request.items.select_for_update():
        if item.quantity_approved is None:
            continue
        received = received_quantities.get(item.pk, item.quantity_approved)
        received = int(received)
        if received < 0 or received > item.quantity_approved:
            raise ReturnError(f"تعدادِ دریافتی برای «{item.order_item.product_name}» نامعتبر است.")
        item.quantity_received = received
        item.save(update_fields=["quantity_received", "updated_at"])

    return_request.received_at = timezone.now()
    return_request.save(update_fields=["status", "actor", "received_at", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="return.received",
        object_type="ReturnRequest", object_id=return_request.pk, object_label=return_request.return_number,
    )
    return return_request


@transaction.atomic
def inspect_return_items(
    return_request: ReturnRequest, *, store, actor=None, inspections: list[dict], inspection_result: str = "",
) -> ReturnRequest:
    """``inspections``: فهرستی از
    ``{"item_id", "condition", "is_restockable", "merchant_resolution", "refund_amount", "rejection_reason"}``."""
    _transition(return_request, ReturnRequest.Status.INSPECTED, store=store, actor=actor)

    items_by_id = {item.pk: item for item in return_request.items.select_for_update()}
    for entry in inspections:
        item = items_by_id.get(entry["item_id"])
        if item is None:
            raise ReturnError("این قلمِ مرجوعی متعلق به این درخواست نیست.")
        item.condition = entry.get("condition", item.condition)
        item.is_restockable = bool(entry.get("is_restockable", item.is_restockable))
        item.merchant_resolution = entry.get("merchant_resolution", item.merchant_resolution)
        if "refund_amount" in entry:
            item.refund_amount = Decimal(str(entry["refund_amount"]))
        item.rejection_reason = entry.get("rejection_reason", item.rejection_reason)
        if "restock_warehouse_id" in entry:
            from apps.catalog.models import Warehouse
            warehouse_id = entry["restock_warehouse_id"]
            item.restock_warehouse = (
                Warehouse.objects.filter(pk=warehouse_id, store=store, is_active=True).first()
                if warehouse_id else None
            )
        item.save(update_fields=[
            "condition", "is_restockable", "merchant_resolution", "refund_amount", "rejection_reason",
            "restock_warehouse", "updated_at",
        ])

    if inspection_result:
        return_request.inspection_result = inspection_result
    return_request.save(update_fields=["status", "actor", "inspection_result", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="return.inspected",
        object_type="ReturnRequest", object_id=return_request.pk, object_label=return_request.return_number,
    )
    return return_request


@transaction.atomic
def complete_return(return_request: ReturnRequest, *, store, actor=None, create_refund: bool = True) -> ReturnRequest:
    """مرجوعی را نهایی می‌کند: برای هر قلمِ قابل‌بازگشت، موجودی را بازمی‌گرداند
    (idempotent — بارِ دوم چیزی اضافه نمی‌کند)، و در صورتِ درخواست، یک
    استرداد برای اقلامی که تصمیمِ مدیر «استرداد وجه» بوده می‌سازد."""
    _transition(return_request, ReturnRequest.Status.COMPLETED, store=store, actor=actor)

    from apps.orders.services.refund_service import execute_order_refund

    line_requests = []
    for item in return_request.items.select_for_update():
        if item.is_restockable and (item.quantity_received or 0) > 0:
            try:
                restock_return_item(store=store, return_item=item, actor=actor)
            except ReturnItemAlreadyRestockedError:
                pass  # قبلاً بازگشته — idempotent

        if item.merchant_resolution == item.Resolution.REFUND and (item.quantity_received or 0) > 0:
            line_requests.append({"order_item_id": item.order_item_id, "quantity": item.quantity_received})

    if create_refund and line_requests and return_request.refund_id is None:
        refund = execute_order_refund(
            return_request.order, store=store, actor=actor, line_requests=line_requests,
            reason=Refund.Reason.CUSTOMER_REQUEST, merchant_note=f"مرجوعی {return_request.return_number}",
            idempotency_key=f"return:{return_request.pk}",
        )
        return_request.refund = refund

    return_request.completed_at = timezone.now()
    return_request.save(update_fields=["status", "actor", "refund", "completed_at", "updated_at"])

    record_audit_event(
        store=store, actor=actor, action_code="return.completed",
        object_type="ReturnRequest", object_id=return_request.pk, object_label=return_request.return_number,
    )
    return return_request
