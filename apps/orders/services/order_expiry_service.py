"""انقضایِ سفارش‌هایِ **آنلاینِ پرداخت‌نشده** (M2) — فقط از مسیرِ موجودِ لغو.

انقضا = لغو (``change_order_status(→canceled)``): موجودی برمی‌گردد، ظرفیتِ کدِ تخفیف آزاد می‌شود
(``release_redemption``)، رخدادِ حسابرسی/تاریخچه ثبت و یک ایمیلِ تراکنشیِ لغو فرستاده می‌شود؛ پیامک
فقط اگر ``ShopSettings.unpaid_expiry_notify_sms`` روشن باشد (پیش‌فرض خاموش).

* پیش‌فرض غیرفعال (``unpaid_online_order_ttl_minutes = 0``) ⇒ هیچ کاری نمی‌کند.
* **COD و هر سفارشِ غیرِ قطعاً-آنلاین هرگز منقضی نمی‌شود.** «آنلاین» یعنی: درگاهِ سفارش با یک
  ``PaymentGatewayConfig`` آنلاین هم‌نام است، یا سفارش دست‌کم یک ``PaymentAttempt`` روی درگاهِ آنلاین دارد.
* سفارشِ دارایِ تلاشِ **موفق** یا تلاشِ بازِ دارایِ فعالیتِ کمتر از مهلتِ تکمیلی (callback در راه) رد می‌شود.
* پیش از لغو، همه‌ی شرط‌ها زیرِ قفلِ ردیفِ سفارش دوباره سنجیده می‌شود (همان ترتیبِ قفلِ callback پرداخت).
* idempotent: سفارشِ لغوشده دیگر کاندید نیست؛ اجرایِ مکرر اثرِ دوباره ندارد."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.core.services.audit_service import record_audit_event
from apps.orders.models import Order, PaymentAttempt, PaymentGatewayConfig
from apps.orders.services.order_service import change_order_status

logger = logging.getLogger(__name__)

OPEN_ATTEMPT_STATUSES = [s for s in PaymentAttempt.Status.values if s not in PaymentAttempt.FINAL_STATUSES]


def _online_config_codes(store) -> set:
    return {
        c.gateway_code for c in PaymentGatewayConfig.objects.filter(store=store) if c.is_online
    }


def is_definitely_online(order: Order, online_codes: set) -> bool:
    gateway = order.payment_gateway
    if gateway is not None and gateway.slug in online_codes:
        return True
    return any(
        a.gateway_config.is_online for a in order.payment_attempts.select_related("gateway_config")
    )


def _skip_reason(order: Order, shop, now, online_codes) -> str:
    """دلیلِ رد (یا ``""`` اگر منقضی‌شدنی است). باید زیرِ قفلِ ردیفِ سفارش صدا زده شود."""
    ttl = timedelta(minutes=shop.unpaid_online_order_ttl_minutes)
    grace = timedelta(minutes=shop.unpaid_online_order_grace_minutes)
    if order.status != Order.Status.PENDING:
        return "status_not_pending"
    if order.payment_status != Order.PaymentStatus.PENDING:
        return "payment_not_pending"
    if order.created_at > now - ttl:
        return "not_old_enough"
    if not is_definitely_online(order, online_codes):
        return "not_online"
    attempts = list(order.payment_attempts.all())
    if any(a.status == PaymentAttempt.Status.SUCCEEDED for a in attempts):
        return "confirmed_payment"
    if any(a.status in OPEN_ATTEMPT_STATUSES and a.updated_at > now - grace for a in attempts):
        return "payment_in_flight"
    return ""


def expire_unpaid_orders(*, store=None, now=None, dry_run: bool = False, batch_size: int = 200) -> dict:
    """→ ``{"candidates", "expired", "skipped": {reason: n}}``."""
    now = now or timezone.now()
    stats = {"candidates": 0, "expired": 0, "skipped": {}}
    shops = ShopSettings.objects.filter(unpaid_online_order_ttl_minutes__gt=0).select_related("store")
    if store is not None:
        shops = shops.filter(store=store)
    for shop in shops:
        online_codes = _online_config_codes(shop.store)
        cutoff = now - timedelta(minutes=shop.unpaid_online_order_ttl_minutes)
        base = Order.objects.filter(
            store=shop.store, status=Order.Status.PENDING, payment_status=Order.PaymentStatus.PENDING, created_at__lte=cutoff,
        ).order_by("pk")
        last_pk = 0
        while True:
            ids = list(base.filter(pk__gt=last_pk).values_list("pk", flat=True)[:batch_size])
            if not ids:
                break
            last_pk = ids[-1]
            for order_id in ids:
                stats["candidates"] += 1
                reason = _expire_one(order_id, shop, now, online_codes, dry_run)
                if reason:
                    stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1
                else:
                    stats["expired"] += 1
    return stats


def _expire_one(order_id: int, shop, now, online_codes, dry_run: bool) -> str:
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related("payment_gateway").get(pk=order_id)
        reason = _skip_reason(order, shop, now, online_codes)
        if reason:
            return reason
        if dry_run:
            return ""
        # تلاش‌هایِ بازِ کهنه نهایی (EXPIRED) می‌شوند؛ callbackِ دیرهنگامِ آن‌ها همچنان راستی‌آزمایی می‌شود (M1).
        order.payment_attempts.filter(status__in=OPEN_ATTEMPT_STATUSES).update(
            status=PaymentAttempt.Status.EXPIRED, failure_code="expired", failure_message="مهلتِ پرداخت به پایان رسید",
            updated_at=now,
        )
        change_order_status(
            order, Order.Status.CANCELED, note="انقضای مهلتِ پرداخت — لغوِ خودکار", store=order.store,
            suppress_sms=not shop.unpaid_expiry_notify_sms,
        )
        record_audit_event(
            store=order.store, actor=None, action_code="order.payment_expired",
            object_type="Order", object_id=order.pk, object_label=order.code,
            after={"ttl_minutes": shop.unpaid_online_order_ttl_minutes, "grace_minutes": shop.unpaid_online_order_grace_minutes},
            request_id=f"expire-{order.pk}",
        )
        return ""
